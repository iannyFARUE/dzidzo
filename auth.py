import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
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

ACCESS_TOKEN_COOKIE = "access_token"

# Single-purpose tokens carry an audience. jwt.decode rejects a token that has an "aud"
# claim unless the caller asks for that audience, so these can never be used as access
# tokens, an access token is never accepted here, and the two kinds can't be swapped.
PASSWORD_RESET_AUDIENCE = "password-reset"
EMAIL_VERIFY_AUDIENCE = "email-verify"


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hasher.verify(password, hashed)


def create_access_token(user_id: int) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=settings.algorithm)


def _password_fingerprint(user: models.User) -> str:
    # Argon2 hashes are salted, so this changes on every password change. Embedding it in
    # a reset token makes the token single-use without storing anything in the database.
    return hashlib.sha256(user.password_hash.encode()).hexdigest()[:16]


def _create_purpose_token(user: models.User, audience: str, minutes: int, **claims: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=minutes)
    payload = {"sub": str(user.id), "aud": audience, "exp": expire, **claims}
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=settings.algorithm)


async def _decode_purpose_token(
    db: AsyncSession, token: str, audience: str, claim: str
) -> tuple[models.User, str] | None:
    """Return the active user a token was issued to, plus the value of its extra claim."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
            audience=audience,
            options={"require": ["exp", "sub", "aud", claim]},
        )
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError):
        return None

    user = await db.get(models.User, user_id)
    if user is None or user.deleted_at is not None:
        return None
    return user, str(payload[claim])


def create_password_reset_token(user: models.User) -> str:
    return _create_purpose_token(
        user, PASSWORD_RESET_AUDIENCE, settings.password_reset_expire_minutes,
        pwd=_password_fingerprint(user),
    )


async def get_user_from_reset_token(db: AsyncSession, token: str) -> models.User | None:
    decoded = await _decode_purpose_token(db, token, PASSWORD_RESET_AUDIENCE, "pwd")
    if decoded is None:
        return None
    user, fingerprint = decoded
    if not hmac.compare_digest(fingerprint, _password_fingerprint(user)):
        return None
    return user


def create_email_verification_token(user: models.User) -> str:
    # The token names the address it was sent to, so it can only ever verify that
    # address, and changing the email makes earlier links useless.
    return _create_purpose_token(
        user, EMAIL_VERIFY_AUDIENCE, settings.email_verify_expire_minutes, email=user.email
    )


async def get_user_from_verification_token(db: AsyncSession, token: str) -> models.User | None:
    decoded = await _decode_purpose_token(db, token, EMAIL_VERIFY_AUDIENCE, "email")
    if decoded is None:
        return None
    user, email = decoded
    if not hmac.compare_digest(email.encode(), user.email.encode()):
        return None
    return user


async def authenticate_user(db: AsyncSession, identifier: str, password: str) -> models.User | None:
    # Usernames can't contain "@", so the identifier matches exactly one column and
    # a username can never shadow another user's email.
    column = models.User.email if "@" in identifier else models.User.username
    user = await db.scalar(
        select(models.User).where(models.User.deleted_at.is_(None), column == identifier)
    )
    if user is None:
        verify_password(password, DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def get_user_from_token(db: AsyncSession, token: str) -> models.User | None:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
            options={"require": ["exp", "sub"]},
        )
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, ValueError):
        return None

    user = await db.get(models.User, user_id)
    if user is None or user.deleted_at is not None:
        return None
    return user


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> models.User:
    user = await get_user_from_token(db, token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_optional_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> models.User | None:
    token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    user = await get_user_from_token(db, token) if token else None
    request.state.current_user = user
    return user


CurrentUser = Annotated[models.User, Depends(get_current_user)]
OptionalUser = Annotated[models.User | None, Depends(get_optional_user)]
