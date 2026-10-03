import re

from pagination import Pagination, paginate
from schemas import (
    Page,
    PostCreate,
    PostReplace,
    PostResponse,
    PostUpdate,
)
from sqlalchemy.ext.asyncio import AsyncSession
import models
from fastapi import Depends, FastAPI, Request, HTTPException, status, APIRouter
from typing import Annotated
from database import get_db
from sqlalchemy import select
from datetime import UTC, datetime
from sqlalchemy.orm import selectinload

from auth import CurrentUser


DbSession = Annotated[AsyncSession, Depends(get_db)]
router = APIRouter()


POST_RELATIONSHIPS = (selectinload(models.Post.author), selectinload(models.Post.tags))
# id breaks ties between posts published at the same instant, so pages never overlap or skip.
NEWEST_FIRST = (models.Post.published_at.desc(), models.Post.id.desc())


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


async def unique_slug(db: AsyncSession, title: str, exclude_post_id: int | None = None) -> str:
    base = slugify(title)
    slug = base
    suffix = 2
    while True:
        query = select(models.Post).where(models.Post.slug == slug)
        if exclude_post_id is not None:
            query = query.where(models.Post.id != exclude_post_id)
        if await db.scalar(query) is None:
            return slug
        slug = f"{base}-{suffix}"
        suffix += 1


async def get_or_create_tags(db: AsyncSession, tag_names: list[str]) -> list[models.Tag]:
    tags = []
    for name in tag_names:
        tag = await db.scalar(select(models.Tag).where(models.Tag.name == name))
        if tag is None:
            tag = models.Tag(name=name)
            db.add(tag)
        tags.append(tag)
    return tags


async def get_active_user(db: AsyncSession, user_id: int) -> models.User | None:
    user = await db.get(models.User, user_id)
    if user is None or user.deleted_at is not None:
        return None
    return user


async def get_owned_post(db: AsyncSession, post_id: int, user: models.User) -> models.Post:
    post = await db.get(models.Post, post_id, options=list(POST_RELATIONSHIPS))
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")
    if post.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not the author of this post")
    return post


@router.get("", response_model=Page[PostResponse])
async def get_posts(db: DbSession, params: Pagination):
    query = select(models.Post).options(*POST_RELATIONSHIPS).order_by(*NEWEST_FIRST)
    return await paginate(db, query, params)


@router.get("/{post_id}", response_model=PostResponse)
async def get_post(post_id: int, db: DbSession):
    post = await db.get(models.Post, post_id, options=list(POST_RELATIONSHIPS))
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="post not found")
    return post


@router.post("/", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def create_post(post_in: PostCreate, db: DbSession, current_user: CurrentUser):
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
    return post


@router.patch("/{post_id}", response_model=PostResponse)
async def update_post(post_id: int, post_in: PostUpdate, db: DbSession, current_user: CurrentUser):
    post = await get_owned_post(db, post_id, current_user)

    updates = post_in.model_dump(exclude_unset=True)

    if "title" in updates:
        post.title = updates["title"]
        post.slug = await unique_slug(db, updates["title"], exclude_post_id=post.id)
    if "subtitle" in updates:
        post.subtitle = updates["subtitle"]
    if "content" in updates:
        post.content = updates["content"]
        post.read_time_minutes = max(1, len(updates["content"].split()) // 200)
    if "cover_image" in updates:
        post.cover_image = updates["cover_image"]
    if "tags" in updates:
        post.tags = await get_or_create_tags(db, updates["tags"])

    await db.commit()
    return post


@router.put("/{post_id}", response_model=PostResponse)
async def replace_post(post_id: int, post_in: PostReplace, db: DbSession, current_user: CurrentUser):
    post = await get_owned_post(db, post_id, current_user)

    post.title = post_in.title
    post.slug = await unique_slug(db, post_in.title, exclude_post_id=post.id)
    post.subtitle = post_in.subtitle
    post.content = post_in.content
    post.cover_image = post_in.cover_image
    post.tags = await get_or_create_tags(db, post_in.tags)
    post.read_time_minutes = max(1, len(post_in.content.split()) // 200)

    await db.commit()
    return post


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(post_id: int, db: DbSession, current_user: CurrentUser):
    post = await get_owned_post(db, post_id, current_user)
    await db.delete(post)
    await db.commit()




@router.get("/{user_id}/posts", response_model=Page[PostResponse])
async def get_user_posts(user_id: int, db: DbSession, params: Pagination):
    user = await get_active_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    query = (
        select(models.Post)
        .options(*POST_RELATIONSHIPS)
        .where(models.Post.user_id == user_id)
        .order_by(*NEWEST_FIRST)
    )
    return await paginate(db, query, params)