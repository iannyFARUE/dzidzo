from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import models
from config import settings
from database import get_db

password_hasher = PasswordHash.recommended()

# Verified against when the user doesn't exist, so a login attempt takes the same
# time whether or not the account exists (prevents username enumeration by timing).
DUMMY_HASH = password_hasher.hash("dummy-password-for-timing")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/users/token")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hasher.verify(password, hashed)


def create_access_token(user_id: int) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=settings.algorithm)


async def authenticate_user(db: AsyncSession, identifier: str, password: str) -> models.User | None:
    user = await db.scalar(
        select(models.User).where(
            models.User.deleted_at.is_(None),
            (models.User.username == identifier) | (models.User.email == identifier),
        )
    )
    if user is None:
        verify_password(password, DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> models.User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
            options={"require": ["exp", "sub"]},
        )
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError):
        raise credentials_error

    user = await db.get(models.User, user_id)
    if user is None or user.deleted_at is not None:
        raise credentials_error
    return user


CurrentUser = Annotated[models.User, Depends(get_current_user)]
