from typing import Annotated
import re
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Request, HTTPException, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

import models
from database import Base, engine, get_db
from schemas import (
    PostCreate,
    PostReplace,
    PostResponse,
    PostUpdate,
    UserCreate,
    UserReplace,
    UserResponse,
    UserRestore,
    UserUpdate,
)

DbSession = Annotated[Session, Depends(get_db)]


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def unique_slug(db: Session, title: str, exclude_post_id: int | None = None) -> str:
    base = slugify(title)
    slug = base
    suffix = 2
    while True:
        query = select(models.Post).where(models.Post.slug == slug)
        if exclude_post_id is not None:
            query = query.where(models.Post.id != exclude_post_id)
        if db.scalar(query) is None:
            return slug
        slug = f"{base}-{suffix}"
        suffix += 1


def get_or_create_tags(db: Session, tag_names: list[str]) -> list[models.Tag]:
    tags = []
    for name in tag_names:
        tag = db.scalar(select(models.Tag).where(models.Tag.name == name))
        if tag is None:
            tag = models.Tag(name=name)
            db.add(tag)
        tags.append(tag)
    return tags


def get_active_user(db: Session, user_id: int) -> models.User | None:
    user = db.get(models.User, user_id)
    if user is None or user.deleted_at is not None:
        return None
    return user


def check_username_email_available(
    db: Session, username: str, email: str, exclude_user_id: int | None = None
) -> None:
    query = select(models.User).where(
        models.User.deleted_at.is_(None),
        (models.User.username == username) | (models.User.email == email),
    )
    if exclude_user_id is not None:
        query = query.where(models.User.id != exclude_user_id)
    if db.scalar(query) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="username or email already registered",
        )


Base.metadata.create_all(bind=engine)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/media", StaticFiles(directory="media"), name="media")

templates = Jinja2Templates(directory="templates")
templates.env.globals["current_year"] = datetime.now().year

@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exception: RequestValidationError):
    if request.url.path.startswith("/api"):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": exception.errors()},
        )

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "title": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "detail": "Invalid request. Please check your input and try again.",
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    message = (
        exc.detail
        if exc.detail
        else "An error occurred. Please check your request and try again."
    )
    if request.url.path.startswith("/api"):
        return JSONResponse({"detail": message}, status_code=exc.status_code)
    return templates.TemplateResponse(
        request,
        "error.html",
        {"status_code": exc.status_code, "detail": message, "title": str(exc.status_code)},
        status_code=exc.status_code,
    )


@app.get("/", include_in_schema=False, name="home")
@app.get("/posts", include_in_schema=False, name="posts")
def home(request: Request, db: DbSession):
    posts = db.scalars(select(models.Post).order_by(models.Post.published_at.desc())).all()
    topics = sorted({tag.name for post in posts for tag in post.tags})
    return templates.TemplateResponse(
        request, "home.html", {"posts": posts, "topics": topics, "title": "Home"}
    )

@app.get("/posts/{slug}", include_in_schema=False, name="post_detail")
def post_detail(request: Request, slug: str, db: DbSession):
    post = db.scalar(select(models.Post).where(models.Post.slug == slug))
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")
    more_posts = db.scalars(
        select(models.Post)
        .where(models.Post.slug != slug)
        .order_by(models.Post.published_at.desc())
        .limit(2)
    ).all()
    return templates.TemplateResponse(
        request,
        "post.html",
        {"post": post, "more_posts": more_posts, "title": post.title},
    )

@app.get("/users/{username}", include_in_schema=False, name="user_posts")
def user_posts(request: Request, username: str, db: DbSession):
    author = db.scalar(
        select(models.User).where(
            models.User.username == username, models.User.deleted_at.is_(None)
        )
    )
    if author is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    posts = db.scalars(
        select(models.Post)
        .where(models.Post.user_id == author.id)
        .order_by(models.Post.published_at.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "user_posts.html",
        {"author": author, "posts": posts, "title": author.name},
    )

@app.get("/api/posts", response_model=list[PostResponse])
def get_posts(db: DbSession):
    return db.scalars(select(models.Post).order_by(models.Post.published_at.desc())).all()


@app.get("/api/posts/{post_id}", response_model=PostResponse)
def get_post(post_id: int, db: DbSession):
    post = db.get(models.Post, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")
    return post


@app.post("/api/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
def create_post(post_in: PostCreate, db: DbSession):
    author = get_active_user(db, post_in.user_id)
    if author is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    post = models.Post(
        slug=unique_slug(db, post_in.title),
        title=post_in.title,
        subtitle=post_in.subtitle,
        content=post_in.content,
        cover_image=post_in.cover_image,
        author=author,
        tags=get_or_create_tags(db, post_in.tags),
        read_time_minutes=max(1, len(post_in.content.split()) // 200),
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post


@app.patch("/api/posts/{post_id}", response_model=PostResponse)
def update_post(post_id: int, post_in: PostUpdate, db: DbSession):
    post = db.get(models.Post, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")

    updates = post_in.model_dump(exclude_unset=True)

    if "title" in updates:
        post.title = updates["title"]
        post.slug = unique_slug(db, updates["title"], exclude_post_id=post.id)
    if "subtitle" in updates:
        post.subtitle = updates["subtitle"]
    if "content" in updates:
        post.content = updates["content"]
        post.read_time_minutes = max(1, len(updates["content"].split()) // 200)
    if "cover_image" in updates:
        post.cover_image = updates["cover_image"]
    if "tags" in updates:
        post.tags = get_or_create_tags(db, updates["tags"])

    db.commit()
    db.refresh(post)
    return post


@app.put("/api/posts/{post_id}", response_model=PostResponse)
def replace_post(post_id: int, post_in: PostReplace, db: DbSession):
    post = db.get(models.Post, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")

    post.title = post_in.title
    post.slug = unique_slug(db, post_in.title, exclude_post_id=post.id)
    post.subtitle = post_in.subtitle
    post.content = post_in.content
    post.cover_image = post_in.cover_image
    post.tags = get_or_create_tags(db, post_in.tags)
    post.read_time_minutes = max(1, len(post_in.content.split()) // 200)

    db.commit()
    db.refresh(post)
    return post


@app.delete("/api/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: int, db: DbSession):
    post = db.get(models.Post, post_id)
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")
    db.delete(post)
    db.commit()


@app.get("/api/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: DbSession):
    user = get_active_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return user


@app.get("/api/users/{user_id}/posts", response_model=list[PostResponse])
def get_user_posts(user_id: int, db: DbSession):
    user = get_active_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return db.scalars(
        select(models.Post)
        .where(models.Post.user_id == user_id)
        .order_by(models.Post.published_at.desc())
    ).all()


@app.post("/api/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user_in: UserCreate, db: DbSession):
    check_username_email_available(db, user_in.username, user_in.email)

    user = models.User(**user_in.model_dump())
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.patch("/api/users/{user_id}", response_model=UserResponse)
def update_user(user_id: int, user_in: UserUpdate, db: DbSession):
    user = get_active_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    updates = user_in.model_dump(exclude_unset=True)
    check_username_email_available(
        db,
        username=updates.get("username", user.username),
        email=updates.get("email", user.email),
        exclude_user_id=user.id,
    )

    for field, value in updates.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user


@app.put("/api/users/{user_id}", response_model=UserResponse)
def replace_user(user_id: int, user_in: UserReplace, db: DbSession):
    user = get_active_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    check_username_email_available(db, user_in.username, user_in.email, exclude_user_id=user.id)

    user.username = user_in.username
    user.name = user_in.name
    user.email = user_in.email
    user.avatar = user_in.avatar

    db.commit()
    db.refresh(user)
    return user


@app.delete("/api/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, db: DbSession):
    user = get_active_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    user.deleted_at = datetime.now(UTC)
    db.commit()


@app.post("/api/users/{user_id}/restore", response_model=UserResponse)
def restore_user(user_id: int, restore_in: UserRestore, db: DbSession):
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if user.deleted_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user is not deleted")

    username = restore_in.username or user.username
    email = restore_in.email or user.email
    check_username_email_available(db, username, email, exclude_user_id=user.id)

    user.username = username
    user.email = email
    user.deleted_at = None

    db.commit()
    db.refresh(user)
    return user
