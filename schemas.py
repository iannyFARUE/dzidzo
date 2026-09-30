from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

TagName = Annotated[str, Field(min_length=1, max_length=30)]

# "@" is reserved for emails so a username can never collide with someone's login email.
USERNAME_PATTERN = r"^[^@]+$"
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+$"


class UserBase(BaseModel):
    username: str = Field(min_length=1, max_length=50, pattern=USERNAME_PATTERN)
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=1, max_length=120, pattern=EMAIL_PATTERN)
    avatar: str = Field(
        default="/media/profile_pics/default.jpg",
        min_length=1,
        max_length=300,
    )


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    name: str
    avatar: str


class UserPrivate(UserPublic):
    email: str


class UserReplace(UserBase):
    pass


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=50, pattern=USERNAME_PATTERN)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, min_length=1, max_length=120, pattern=EMAIL_PATTERN)
    avatar: str | None = Field(default=None, min_length=1, max_length=300)


class UserRestore(BaseModel):
    password: str = Field(min_length=1)
    username: str | None = Field(default=None, min_length=1, max_length=50, pattern=USERNAME_PATTERN)
    email: str | None = Field(default=None, min_length=1, max_length=120, pattern=EMAIL_PATTERN)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


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
    author: UserPublic
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
    pass


class PostReplace(PostBase):
    pass


class PostUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    subtitle: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1)
    cover_image: str | None = Field(default=None, min_length=1, max_length=300)
    tags: list[TagName] | None = Field(default=None, max_length=10)

