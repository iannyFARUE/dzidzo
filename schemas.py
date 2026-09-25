from datetime import datetime

from pydantic import BaseModel


class Author(BaseModel):
    id: int
    name: str
    username: str
    avatar: str


class PostResponse(BaseModel):
    id: int
    slug: str
    title: str
    subtitle: str
    content: str
    cover_image: str
    author: Author
    tags: list[str]
    claps: int
    comments_count: int
    read_time_minutes: int
    published_at: datetime
    updated_at: datetime


class PostCreate(BaseModel):
    title: str
    subtitle: str
    content: str
    cover_image: str
    tags: list[str] = []
