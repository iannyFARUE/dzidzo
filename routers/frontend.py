from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import avatars
import models
import schemas
from auth import (
    ACCESS_TOKEN_COOKIE,
    OptionalUser,
    authenticate_user,
    create_access_token,
    get_optional_user,
    hash_password,
)
from config import settings
from database import get_db
from pagination import PageParams, PageResult, Pagination, paginate
from routers.posts import NEWEST_FIRST, get_or_create_tags, unique_slug
from routers.users import check_username_email_available
from storage import Storage, get_storage
from templating import templates

DbSession = Annotated[AsyncSession, Depends(get_db)]
StorageDep = Annotated[Storage, Depends(get_storage)]
router = APIRouter(dependencies=[Depends(get_optional_user)])

POST_RELATIONSHIPS = (selectinload(models.Post.author), selectinload(models.Post.tags))
TOPIC_LIMIT = 12


async def paginate_or_404(db: AsyncSession, query, params: PageParams) -> PageResult:
    page = await paginate(db, query, params)
    # Page 1 of an empty list is a valid (empty) page; anything past the end isn't.
    if params.page > 1 and not page.items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="page not found")
    return page


def safe_next(next_url: str | None) -> str:
    # Only allow same-site relative paths, so ?next= can't be used as an open redirect.
    if next_url and next_url.startswith("/") and not next_url.startswith(("//", "/\\")):
        return next_url
    return "/"


PATTERN_MESSAGES = {
    "username": "Usernames can't contain @.",
    "email": "Enter a valid email address.",
}


def form_errors(exc: ValidationError) -> dict[str, str]:
    errors = {}
    for error in exc.errors():
        field = error["loc"][0]
        if error["type"] == "string_pattern_mismatch" and field in PATTERN_MESSAGES:
            errors[field] = PATTERN_MESSAGES[field]
        else:
            errors[field] = error["msg"]
    return errors


def login_redirect(request: Request, next_path: str | None = None) -> RedirectResponse:
    url = request.url_for("login_form").include_query_params(next=next_path or request.url.path)
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def set_auth_cookie(request: Request, response: RedirectResponse, user: models.User) -> None:
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        create_access_token(user.id),
        max_age=settings.access_token_expire_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )


async def get_post_for_owner(db: AsyncSession, slug: str, user: models.User) -> models.Post:
    post = await db.scalar(
        select(models.Post).options(*POST_RELATIONSHIPS).where(models.Post.slug == slug)
    )
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")
    if post.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only change your own stories.")
    return post


@router.get("/", include_in_schema=False, name="home")
@router.get("/posts", include_in_schema=False, name="posts")
async def home(request: Request, db: DbSession, params: Pagination):
    page = await paginate_or_404(
        db, select(models.Post).options(*POST_RELATIONSHIPS).order_by(*NEWEST_FIRST), params
    )
    # Topics come from the whole site, not just the posts on this page.
    topics = (
        await db.scalars(
            select(models.Tag.name)
            .join(models.post_tags)
            .group_by(models.Tag.id)
            .order_by(func.count().desc(), models.Tag.name)
            .limit(TOPIC_LIMIT)
        )
    ).all()
    return templates.TemplateResponse(
        request, "home.html", {"posts": page.items, "page": page, "topics": topics, "title": "Home"}
    )


@router.get("/posts/{slug}", include_in_schema=False, name="post_detail")
async def post_detail(request: Request, slug: str, db: DbSession, current_user: OptionalUser):
    post = await db.scalar(
        select(models.Post).options(*POST_RELATIONSHIPS).where(models.Post.slug == slug)
    )
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")
    more_posts = (
        await db.scalars(
            select(models.Post)
            .options(*POST_RELATIONSHIPS)
            .where(models.Post.slug != slug)
            .order_by(models.Post.published_at.desc())
            .limit(2)
        )
    ).all()
    return templates.TemplateResponse(
        request,
        "post.html",
        {
            "post": post,
            "more_posts": more_posts,
            "title": post.title,
            "is_owner": current_user is not None and post.user_id == current_user.id,
        },
    )


@router.get("/users/{username}", include_in_schema=False, name="user_posts")
async def user_posts(request: Request, username: str, db: DbSession, params: Pagination):
    author = await db.scalar(
        select(models.User).where(
            models.User.username == username, models.User.deleted_at.is_(None)
        )
    )
    if author is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    page = await paginate_or_404(
        db,
        select(models.Post)
        .options(selectinload(models.Post.tags))
        .where(models.Post.user_id == author.id)
        .order_by(*NEWEST_FIRST),
        params,
    )
    return templates.TemplateResponse(
        request,
        "user_posts.html",
        {"author": author, "posts": page.items, "page": page, "title": author.name},
    )


@router.get("/login", include_in_schema=False, name="login_form")
async def login_form(request: Request, current_user: OptionalUser, next: str = "/"):
    if current_user is not None:
        return RedirectResponse(safe_next(next), status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request, "login.html", {"title": "Sign in", "next": safe_next(next)}
    )


@router.post("/login", include_in_schema=False, name="login")
async def login(
    request: Request,
    db: DbSession,
    username: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "/",
):
    user = await authenticate_user(db, username.strip(), password)
    if user is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "title": "Sign in",
                "next": safe_next(next),
                "username": username,
                "error": "Incorrect username or password.",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    response = RedirectResponse(safe_next(next), status_code=status.HTTP_303_SEE_OTHER)
    set_auth_cookie(request, response, user)
    return response


@router.get("/register", include_in_schema=False, name="register_form")
async def register_form(request: Request, current_user: OptionalUser, next: str = "/"):
    if current_user is not None:
        return RedirectResponse(safe_next(next), status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request, "register.html", {"title": "Create an account", "next": safe_next(next)}
    )


@router.post("/register", include_in_schema=False, name="register")
async def register(
    request: Request,
    db: DbSession,
    name: Annotated[str, Form()] = "",
    username: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    next: Annotated[str, Form()] = "/",
):
    values = {"name": name, "username": username, "email": email}

    def render_errors(errors: dict[str, str], status_code: int):
        return templates.TemplateResponse(
            request,
            "register.html",
            {
                "title": "Create an account",
                "next": safe_next(next),
                "values": values,
                "errors": errors,
            },
            status_code=status_code,
        )

    try:
        user_in = schemas.UserCreate(
            name=name.strip(), username=username.strip(), email=email.strip(), password=password
        )
    except ValidationError as exc:
        return render_errors(form_errors(exc), status.HTTP_422_UNPROCESSABLE_CONTENT)

    try:
        await check_username_email_available(db, user_in.username, user_in.email)
    except HTTPException:
        return render_errors(
            {"form": "That username or email is already registered."},
            status.HTTP_409_CONFLICT,
        )

    user = models.User(
        **user_in.model_dump(exclude={"password"}),
        password_hash=hash_password(user_in.password),
    )
    db.add(user)
    await db.commit()

    response = RedirectResponse(safe_next(next), status_code=status.HTTP_303_SEE_OTHER)
    set_auth_cookie(request, response, user)
    return response


PROFILE_NOTICES = {
    "details": "Your profile has been updated.",
    "avatar": "Your profile photo has been updated.",
    "avatar_removed": "Your profile photo has been removed.",
}


def render_profile(
    request: Request,
    user: models.User,
    *,
    values: dict | None = None,
    errors: dict | None = None,
    notice: str | None = None,
    status_code: int = status.HTTP_200_OK,
):
    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "title": "Your profile",
            "user": user,
            "values": values or {"name": user.name, "username": user.username, "email": user.email},
            "errors": errors or {},
            "notice": notice,
            "is_default_avatar": user.avatar == avatars.DEFAULT_AVATAR,
            "max_avatar_mb": settings.max_avatar_bytes // (1024 * 1024),
        },
        status_code=status_code,
    )


def profile_redirect(request: Request, saved: str) -> RedirectResponse:
    url = request.url_for("profile").include_query_params(saved=saved)
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/profile", include_in_schema=False, name="profile")
async def profile(request: Request, current_user: OptionalUser, saved: str | None = None):
    if current_user is None:
        return login_redirect(request)
    return render_profile(request, current_user, notice=PROFILE_NOTICES.get(saved or ""))


@router.post("/profile", include_in_schema=False, name="update_profile")
async def update_profile(
    request: Request,
    db: DbSession,
    current_user: OptionalUser,
    name: Annotated[str, Form()] = "",
    username: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
):
    if current_user is None:
        return login_redirect(request)

    values = {"name": name, "username": username, "email": email}
    try:
        user_in = schemas.UserUpdate(name=name.strip(), username=username.strip(), email=email.strip())
    except ValidationError as exc:
        return render_profile(
            request, current_user, values=values, errors=form_errors(exc),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    try:
        await check_username_email_available(
            db, user_in.username, user_in.email, exclude_user_id=current_user.id
        )
    except HTTPException:
        return render_profile(
            request, current_user, values=values,
            errors={"details": "That username or email is already registered."},
            status_code=status.HTTP_409_CONFLICT,
        )

    current_user.name = user_in.name
    current_user.username = user_in.username
    current_user.email = user_in.email
    await db.commit()
    return profile_redirect(request, "details")


@router.post("/profile/avatar", include_in_schema=False, name="update_avatar")
async def update_avatar(
    request: Request,
    db: DbSession,
    storage: StorageDep,
    current_user: OptionalUser,
    avatar: Annotated[UploadFile | None, File()] = None,
):
    if current_user is None:
        return login_redirect(request, next_path="/profile")
    try:
        if avatar is None:
            raise avatars.AvatarError("Please choose an image to upload.")
        await avatars.set_avatar(db, storage, current_user, avatar)
    except avatars.AvatarError as exc:
        return render_profile(
            request, current_user, errors={"avatar": str(exc)},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
    return profile_redirect(request, "avatar")


@router.post("/profile/avatar/delete", include_in_schema=False, name="remove_avatar")
async def remove_avatar(request: Request, db: DbSession, storage: StorageDep, current_user: OptionalUser):
    if current_user is None:
        return login_redirect(request, next_path="/profile")
    await avatars.reset_avatar(db, storage, current_user)
    return profile_redirect(request, "avatar_removed")


@router.post("/logout", include_in_schema=False, name="logout")
async def logout():
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(ACCESS_TOKEN_COOKIE)
    return response


def _parse_tags(tags: str) -> list[str]:
    return [name.strip() for name in tags.split(",") if name.strip()]


def _form_values(title: str, subtitle: str, content: str, cover_image: str, tag_names: list[str]) -> dict:
    return {
        "title": title,
        "subtitle": subtitle,
        "content": content,
        "cover_image": cover_image,
        "tags": ", ".join(tag_names),
    }


@router.get("/write", include_in_schema=False, name="new_post_form")
async def new_post_form(request: Request, current_user: OptionalUser):
    if current_user is None:
        return login_redirect(request)
    return templates.TemplateResponse(
        request,
        "post_form.html",
        {
            "title": "Write a story",
            "heading": "New story",
            "submit_label": "Publish",
            "form_action": request.url_for("create_post_form"),
        },
    )


@router.post("/write", include_in_schema=False, name="create_post_form")
async def create_post_form(
    request: Request,
    db: DbSession,
    current_user: OptionalUser,
    title: Annotated[str, Form()] = "",
    subtitle: Annotated[str, Form()] = "",
    content: Annotated[str, Form()] = "",
    cover_image: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
):
    if current_user is None:
        return login_redirect(request)

    tag_names = _parse_tags(tags)
    values = _form_values(title, subtitle, content, cover_image, tag_names)

    try:
        post_in = schemas.PostBase(
            title=title,
            subtitle=subtitle,
            content=content,
            cover_image=cover_image,
            tags=tag_names,
        )
    except ValidationError as exc:
        errors = {error["loc"][0]: error["msg"] for error in exc.errors()}
        return templates.TemplateResponse(
            request,
            "post_form.html",
            {
                "title": "Write a story",
                "heading": "New story",
                "submit_label": "Publish",
                "form_action": request.url_for("create_post_form"),
                "errors": errors,
                "values": values,
            },
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    post = models.Post(
        slug=await unique_slug(db, post_in.title),
        title=post_in.title,
        subtitle=post_in.subtitle,
        content=post_in.content,
        cover_image=post_in.cover_image,
        author=current_user,
        tags=await get_or_create_tags(db, post_in.tags),
        read_time_minutes=max(1, len(post_in.content.split()) // 200),
    )
    db.add(post)
    await db.commit()

    return RedirectResponse(
        request.url_for("post_detail", slug=post.slug), status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/posts/{slug}/edit", include_in_schema=False, name="edit_post_form")
async def edit_post_form(request: Request, slug: str, db: DbSession, current_user: OptionalUser):
    if current_user is None:
        return login_redirect(request)
    post = await get_post_for_owner(db, slug, current_user)

    values = _form_values(
        post.title, post.subtitle, post.content, post.cover_image, [tag.name for tag in post.tags]
    )
    return templates.TemplateResponse(
        request,
        "post_form.html",
        {
            "title": f'Edit "{post.title}"',
            "heading": "Edit story",
            "submit_label": "Update",
            "form_action": request.url_for("update_post_form", slug=post.slug),
            "delete_action": request.url_for("delete_post_form", slug=post.slug),
            "values": values,
        },
    )


@router.post("/posts/{slug}/edit", include_in_schema=False, name="update_post_form")
async def update_post_form(
    request: Request,
    slug: str,
    db: DbSession,
    current_user: OptionalUser,
    title: Annotated[str, Form()] = "",
    subtitle: Annotated[str, Form()] = "",
    content: Annotated[str, Form()] = "",
    cover_image: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
):
    if current_user is None:
        return login_redirect(request)
    post = await get_post_for_owner(db, slug, current_user)

    tag_names = _parse_tags(tags)
    values = _form_values(title, subtitle, content, cover_image, tag_names)

    try:
        post_in = schemas.PostBase(
            title=title,
            subtitle=subtitle,
            content=content,
            cover_image=cover_image,
            tags=tag_names,
        )
    except ValidationError as exc:
        errors = {error["loc"][0]: error["msg"] for error in exc.errors()}
        return templates.TemplateResponse(
            request,
            "post_form.html",
            {
                "title": f'Edit "{post.title}"',
                "heading": "Edit story",
                "submit_label": "Update",
                "form_action": request.url_for("update_post_form", slug=post.slug),
                "delete_action": request.url_for("delete_post_form", slug=post.slug),
                "errors": errors,
                "values": values,
            },
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    post.title = post_in.title
    post.slug = await unique_slug(db, post_in.title, exclude_post_id=post.id)
    post.subtitle = post_in.subtitle
    post.content = post_in.content
    post.cover_image = post_in.cover_image
    post.tags = await get_or_create_tags(db, post_in.tags)
    post.read_time_minutes = max(1, len(post_in.content.split()) // 200)

    await db.commit()

    return RedirectResponse(
        request.url_for("post_detail", slug=post.slug), status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/posts/{slug}/delete", include_in_schema=False, name="delete_post_form")
async def delete_post_form(request: Request, slug: str, db: DbSession, current_user: OptionalUser):
    if current_user is None:
        return login_redirect(request, next_path=f"/posts/{slug}")
    post = await get_post_for_owner(db, slug, current_user)
    await db.delete(post)
    await db.commit()
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
