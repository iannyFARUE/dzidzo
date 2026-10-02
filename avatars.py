import io
from uuid import uuid4

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

import models
from config import settings
from storage import Storage

DEFAULT_AVATAR = "/media/profile_pics/default.jpg"
AVATAR_SIZE = 256
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}

# Reject decompression bombs: a tiny file that expands to an enormous bitmap.
Image.MAX_IMAGE_PIXELS = 40_000_000


class AvatarError(ValueError):
    """The upload isn't an acceptable image. The message is safe to show to the user."""


def _process(data: bytes) -> bytes:
    # Re-encoding (rather than storing the upload as-is) strips EXIF/GPS metadata and
    # anything smuggled alongside the pixels, and guarantees the file really is an image.
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ALLOWED_FORMATS:
                raise AvatarError("Please upload a JPEG, PNG, WebP or GIF image.")
            image = ImageOps.exif_transpose(image)
            image = ImageOps.fit(image.convert("RGB"), (AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise AvatarError("That file isn't a valid image.") from exc

    out = io.BytesIO()
    image.save(out, format="WEBP", quality=85)
    return out.getvalue()


async def read_upload(upload: UploadFile) -> bytes:
    data = await upload.read(settings.max_avatar_bytes + 1)
    if not data:
        raise AvatarError("Please choose an image to upload.")
    if len(data) > settings.max_avatar_bytes:
        raise AvatarError(f"Images must be {settings.max_avatar_bytes // (1024 * 1024)} MB or smaller.")
    return data


async def set_avatar(db: AsyncSession, storage: Storage, user: models.User, upload: UploadFile) -> None:
    image = await run_in_threadpool(_process, await read_upload(upload))
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
