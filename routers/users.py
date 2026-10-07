from fastapi.security import OAuth2PasswordRequestForm

from auth import (
    DUMMY_HASH,
    CurrentUser,
    authenticate_user,
    create_access_token,
    create_email_verification_token,
    create_password_reset_token,
    get_user_from_reset_token,
    get_user_from_verification_token,
    hash_password,
    verify_password,
)
from schemas import (
    EmailVerify,
    Message,
    PasswordForgot,
    PasswordReset,
    Token,
    UserCreate,
    UserPrivate,
    UserPublic,
    UserReplace,
    UserRestore,
    UserUpdate,
)
from sqlalchemy.ext.asyncio import AsyncSession
import avatars
import images
import mail
import models
from fastapi import BackgroundTasks, Depends, FastAPI, Request, HTTPException, UploadFile, status, APIRouter
from typing import Annotated
from database import get_db
from sqlalchemy import select
from storage import Storage, get_storage
DbSession = Annotated[AsyncSession, Depends(get_db)]
StorageDep = Annotated[Storage, Depends(get_storage)]
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


FORGOT_PASSWORD_MESSAGE = "If an account uses that email, a password reset link is on its way."


async def request_password_reset(db: AsyncSession, background_tasks: BackgroundTasks, email: str) -> None:
    # Callers respond the same whether or not the account exists, and the email goes out
    # after the response, so neither the reply nor its timing reveals who has an account.
    user = await db.scalar(
        select(models.User).where(models.User.deleted_at.is_(None), models.User.email == email)
    )
    if user is not None:
        background_tasks.add_task(
            mail.send_password_reset_email, user.email, user.name, create_password_reset_token(user)
        )


async def reset_password(db: AsyncSession, token: str, new_password: str) -> models.User | None:
    user = await get_user_from_reset_token(db, token)
    if user is None:
        return None
    user.password_hash = hash_password(new_password)
    await db.commit()
    return user


def send_verification(background_tasks: BackgroundTasks, user: models.User) -> None:
    background_tasks.add_task(
        mail.send_verification_email, user.email, user.name, create_email_verification_token(user)
    )


def change_email(background_tasks: BackgroundTasks, user: models.User, email: str) -> None:
    """Set a new email; a changed address starts unverified and gets a fresh link."""
    if email == user.email:
        return
    user.email = email
    user.email_verified_at = None
    send_verification(background_tasks, user)


async def verify_email(db: AsyncSession, token: str) -> models.User | None:
    user = await get_user_from_verification_token(db, token)
    if user is None:
        return None
    # Following the link again is harmless and keeps the original verification time.
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
        await db.commit()
    return user


def ensure_self(user_id: int, current_user: models.User) -> None:
    if user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cannot modify another user")

@router.post("", response_model=UserPrivate, status_code=status.HTTP_201_CREATED)
async def create_user(user_in: UserCreate, db: DbSession, background_tasks: BackgroundTasks):
    await check_username_email_available(db, user_in.username, user_in.email)

    user = models.User(
        **user_in.model_dump(exclude={"password"}),
        password_hash=hash_password(user_in.password),
    )
    db.add(user)
    await db.commit()
    send_verification(background_tasks, user)
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


@router.post("/forgot-password", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(body: PasswordForgot, db: DbSession, background_tasks: BackgroundTasks):
    await request_password_reset(db, background_tasks, body.email)
    return Message(detail=FORGOT_PASSWORD_MESSAGE)


@router.post("/reset-password", response_model=Message)
async def reset_password_endpoint(body: PasswordReset, db: DbSession):
    if await reset_password(db, body.token, body.new_password) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reset link is invalid or has expired",
        )
    return Message(detail="password has been reset")


@router.post("/verify-email", response_model=UserPrivate)
async def verify_email_endpoint(body: EmailVerify, db: DbSession):
    user = await verify_email(db, body.token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="verification link is invalid or has expired",
        )
    return user


@router.post("/me/verify-email", response_model=Message, status_code=status.HTTP_202_ACCEPTED)
async def resend_verification(current_user: CurrentUser, background_tasks: BackgroundTasks):
    if current_user.email_verified_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email is already verified")
    send_verification(background_tasks, current_user)
    return Message(detail="verification email sent")


@router.get("/me", response_model=UserPrivate)
async def read_me(current_user: CurrentUser):
    return current_user


@router.put("/me/avatar", response_model=UserPrivate)
async def upload_avatar(file: UploadFile, db: DbSession, storage: StorageDep, current_user: CurrentUser):
    try:
        await avatars.set_avatar(db, storage, current_user, file)
    except images.ImageError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    return current_user


@router.delete("/me/avatar", response_model=UserPrivate)
async def remove_avatar(db: DbSession, storage: StorageDep, current_user: CurrentUser):
    await avatars.reset_avatar(db, storage, current_user)
    return current_user


@router.get("/{user_id}", response_model=UserPublic)
async def get_user(user_id: int, db: DbSession):
    user = await get_active_user(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return user

@router.patch("/{user_id}", response_model=UserPrivate)
async def update_user(
    user_id: int, user_in: UserUpdate, db: DbSession, current_user: CurrentUser, background_tasks: BackgroundTasks
):
    ensure_self(user_id, current_user)
    user = current_user

    updates = user_in.model_dump(exclude_unset=True)
    await check_username_email_available(
        db,
        username=updates.get("username", user.username),
        email=updates.get("email", user.email),
        exclude_user_id=user.id,
    )

    if "email" in updates:
        change_email(background_tasks, user, updates.pop("email"))
    for field, value in updates.items():
        setattr(user, field, value)

    await db.commit()
    return user


@router.put("/{user_id}", response_model=UserPrivate)
async def replace_user(
    user_id: int, user_in: UserReplace, db: DbSession, current_user: CurrentUser, background_tasks: BackgroundTasks
):
    ensure_self(user_id, current_user)
    user = current_user

    await check_username_email_available(db, user_in.username, user_in.email, exclude_user_id=user.id)

    user.username = user_in.username
    user.name = user_in.name
    change_email(background_tasks, user, user_in.email)

    await db.commit()
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, db: DbSession, current_user: CurrentUser):
    ensure_self(user_id, current_user)
    current_user.deleted_at = datetime.now(UTC)
    await db.commit()


@router.post("/{user_id}/restore", response_model=UserPrivate)
async def restore_user(user_id: int, restore_in: UserRestore, db: DbSession, background_tasks: BackgroundTasks):
    # Missing, active and wrong-password cases all fail identically (and take the same
    # time), so this endpoint can't be used to probe accounts or test passwords.
    user = await db.get(models.User, user_id)
    password_ok = verify_password(restore_in.password, user.password_hash if user else DUMMY_HASH)
    if user is None or user.deleted_at is None or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials or account cannot be restored",
        )

    username = restore_in.username or user.username
    email = restore_in.email or user.email
    await check_username_email_available(db, username, email, exclude_user_id=user.id)

    user.username = username
    change_email(background_tasks, user, email)
    user.deleted_at = None

    await db.commit()
    return user