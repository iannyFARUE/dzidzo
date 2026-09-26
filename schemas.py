from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

TagName = Annotated[str, Field(min_length=1, max_length=30)]


class UserBase(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=1, max_length=120)
    avatar: str = Field(
        default="/static/profile_pics/default.jpg",
        min_length=1,
        max_length=300,
    )


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(gt=0)


class Author(UserResponse):
    pass


class PostBase(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    subtitle: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    cover_image: str = Field(min_length=1, max_length=300)
    tags: list[TagName] = Field(default_factory=list, max_length=10)


class PostResponse(PostBase):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(gt=0)
    slug: str = Field(min_length=1, max_length=150)
    author: Author
    claps: int = Field(ge=0)
    comments_count: int = Field(ge=0)
    read_time_minutes: int = Field(ge=1)
    published_at: datetime
    updated_at: datetime

    @field_validator("tags", mode="before")
    @classmethod
    def _tag_names(cls, tags: list) -> list[str]:
        return [tag.name if hasattr(tag, "name") else tag for tag in tags]


class PostCreate(PostBase):
    user_id: int = Field(gt=0)
