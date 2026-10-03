from uuid import uuid4

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageOps
from sqlalchemy.ext.asyncio import AsyncSession

import images
import models
from config import settings
from storage import Storage

DEFAULT_AVATAR = "/media/profile_pics/default.jpg"
AVATAR_SIZE = 256


def _square(image: Image.Image) -> Image.Image:
    return ImageOps.fit(image, (AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)


async def set_avatar(db: AsyncSession, storage: Storage, user: models.User, upload: UploadFile) -> None:
    data = await images.read_upload(upload, settings.max_avatar_bytes)
    image = await run_in_threadpool(images.reencode, data, _square)
    new_url = await storage.save(f"profile_pics/{uuid4().hex}.webp", image, "image/webp")
    await _replace_avatar(db, storage, user, new_url)


async def reset_avatar(db: AsyncSession, storage: Storage, user: models.User) -> None:
    await _replace_avatar(db, storage, user, DEFAULT_AVATAR)


async def _replace_avatar(db: AsyncSession, storage: Storage, user: models.User, new_url: str) -> None:
    old_url = user.avatar
    user.avatar = new_url
    try:
        await db.commit()
    except Exception:
        if new_url != DEFAULT_AVATAR:
            await storage.delete(new_url)
        raise
    # Only remove the old file once the database points at the new one.
    if old_url != DEFAULT_AVATAR and old_url != new_url:
        await storage.delete(old_url)
