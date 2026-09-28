from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import models
import schemas
from database import get_db
from routers.posts import get_or_create_tags, unique_slug
from templating import templates

DbSession = Annotated[AsyncSession, Depends(get_db)]
router = APIRouter()

POST_RELATIONSHIPS = (selectinload(models.Post.author), selectinload(models.Post.tags))

# TODO: replace with the authenticated user once auth is added.
NEW_POST_AUTHOR_USERNAME = "juju"


@router.get("/", include_in_schema=False, name="home")
@router.get("/posts", include_in_schema=False, name="posts")
async def home(request: Request, db: DbSession):
    posts = (
        await db.scalars(
            select(models.Post)
            .options(*POST_RELATIONSHIPS)
            .order_by(models.Post.published_at.desc())
        )
    ).all()
    topics = sorted({tag.name for post in posts for tag in post.tags})
    return templates.TemplateResponse(
        request, "home.html", {"posts": posts, "topics": topics, "title": "Home"}
    )


@router.get("/posts/{slug}", include_in_schema=False, name="post_detail")
async def post_detail(request: Request, slug: str, db: DbSession):
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
        {"post": post, "more_posts": more_posts, "title": post.title},
    )


@router.get("/users/{username}", include_in_schema=False, name="user_posts")
async def user_posts(request: Request, username: str, db: DbSession):
    author = await db.scalar(
        select(models.User).where(
            models.User.username == username, models.User.deleted_at.is_(None)
        )
    )
    if author is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    posts = (
        await db.scalars(
            select(models.Post)
            .options(selectinload(models.Post.tags))
            .where(models.Post.user_id == author.id)
            .order_by(models.Post.published_at.desc())
        )
    ).all()
    return templates.TemplateResponse(
        request,
        "user_posts.html",
        {"author": author, "posts": posts, "title": author.name},
    )


@router.get("/write", include_in_schema=False, name="new_post_form")
async def new_post_form(request: Request):
    return templates.TemplateResponse(request, "new_post.html", {"title": "Write a story"})


@router.post("/write", include_in_schema=False, name="create_post_form")
async def create_post_form(
    request: Request,
    db: DbSession,
    title: Annotated[str, Form()] = "",
    subtitle: Annotated[str, Form()] = "",
    content: Annotated[str, Form()] = "",
    cover_image: Annotated[str, Form()] = "",
    tags: Annotated[str, Form()] = "",
):
    tag_names = [name.strip() for name in tags.split(",") if name.strip()]
    values = {
        "title": title,
        "subtitle": subtitle,
        "content": content,
        "cover_image": cover_image,
        "tags": ", ".join(tag_names),
    }

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
            "new_post.html",
            {"title": "Write a story", "errors": errors, "values": values},
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    author = await db.scalar(
        select(models.User).where(
            models.User.username == NEW_POST_AUTHOR_USERNAME,
            models.User.deleted_at.is_(None),
        )
    )
    if author is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="default author not found")

    post = models.Post(
        slug=await unique_slug(db, post_in.title),
        title=post_in.title,
        subtitle=post_in.subtitle,
        content=post_in.content,
        cover_image=post_in.cover_image,
        author=author,
        tags=await get_or_create_tags(db, post_in.tags),
        read_time_minutes=max(1, len(post_in.content.split()) // 200),
    )
    db.add(post)
    await db.commit()

    return RedirectResponse(
        request.url_for("post_detail", slug=post.slug), status_code=status.HTTP_303_SEE_OTHER
    )
