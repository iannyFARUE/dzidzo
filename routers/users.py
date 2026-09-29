from fastapi.security import OAuth2PasswordRequestForm

from auth import CurrentUser, authenticate_user, create_access_token, hash_password
from schemas import (
    Token,
    UserCreate,
    UserReplace,
    UserResponse,
    UserRestore,
    UserUpdate,
)
from sqlalchemy.ext.asyncio import AsyncSession
import models
from fastapi import Depends, FastAPI, Request, HTTPException, status, APIRouter
from typing import Annotated
from database import get_db
from sqlalchemy import select
DbSession = Annotated[AsyncSession, Depends(get_db)]
router = APIRouter()
from datetime import UTC, datetime

async def check_username_email_available(
    db: AsyncSession, username: str, email: str, exclude_user_id: int | None = None
) -> None:
    query = select(models.User).where(
        models.User.deleted_at.is_(None),
        (models.User.username == username) | (models.User.email == email),
    )
    if exclude_user_id is not None:
        query = query.where(models.User.id != exclude_user_id)
    if await db.scalar(query) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="username or email already registered",
        )

async def get_active_user(db: AsyncSession, user_id: int) -> models.User | None:
    user = await db.get(models.User, user_id)
    if user is None or user.deleted_at is not None:
        return None
    return user

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user_in: UserCreate, db: DbSession):
    await check_username_email_available(db, user_in.username, user_in.email)

    user = models.User(
        **user_in.model_dump(exclude={"password"}),
        password_hash=hash_password(user_in.password),
    )
    db.add(user)
    await db.commit()
    return user


@router.post("/token", response_model=Token)
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    user = await authenticate_user(db, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserResponse)
async def read_me(current_user: CurrentUser):
    return current_user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: DbSession):
    user = await get_active_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return user

@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user_in: UserUpdate, db: DbSession):
    user = await get_active_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    updates = user_in.model_dump(exclude_unset=True)
    await check_username_email_available(
        db,
        username=updates.get("username", user.username),
        email=updates.get("email", user.email),
        exclude_user_id=user.id,
    )

    for field, value in updates.items():
        setattr(user, field, value)

    await db.commit()
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def replace_user(user_id: int, user_in: UserReplace, db: DbSession):
    user = await get_active_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    await check_username_email_available(db, user_in.username, user_in.email, exclude_user_id=user.id)

    user.username = user_in.username
    user.name = user_in.name
    user.email = user_in.email
    user.avatar = user_in.avatar

    await db.commit()
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: DbSession):
    user = await get_active_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")

    user.deleted_at = datetime.now(UTC)
    await db.commit()


@router.post("/{user_id}/restore", response_model=UserResponse)
async def restore_user(user_id: int, restore_in: UserRestore, db: DbSession):
    user = await db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if user.deleted_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user is not deleted")

    username = restore_in.username or user.username
    email = restore_in.email or user.email
    await check_username_email_available(db, username, email, exclude_user_id=user.id)

    user.username = username
    user.email = email
    user.deleted_at = None

    await db.commit()
    return user