from datetime import datetime

from pydantic import BaseModel, Field


class Author(BaseModel):
    id: int
    name: str
    username: str
    avatar: str


class PostBase(BaseModel):
    title: str
    subtitle: str
    content: str
    cover_image: str
    tags: list[str] = []


class PostResponse(PostBase):
    id: int
    slug: str
    author: Author
    claps: int
    comments_count: int
    read_time_minutes: int
    published_at: datetime
    updated_at: datetime


class PostCreate(PostBase):
    pass
