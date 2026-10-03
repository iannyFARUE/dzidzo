from uuid import uuid4

from fastapi import UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageOps
from sqlalchemy.ext.asyncio import AsyncSession

import images
from config import settings
from storage import Storage

# Covers keep their aspect ratio (the story page shows them whole; lists crop thumbnails
# with CSS) and are only ever scaled down.
COVER_MAX_SIZE = (1600, 1600)


def _fit(image: Image.Image) -> Image.Image:
    if image.width <= COVER_MAX_SIZE[0] and image.height <= COVER_MAX_SIZE[1]:
        return image
    return ImageOps.contain(image, COVER_MAX_SIZE, Image.Resampling.LANCZOS)


async def store_cover(storage: Storage, upload: UploadFile) -> str:
    """Validate, resize and save an uploaded cover. Returns its URL; raises images.ImageError."""
    data = await images.read_upload(upload, settings.max_cover_bytes)
    image = await run_in_threadpool(images.reencode, data, _fit)
    return await storage.save(f"covers/{uuid4().hex}.webp", image, "image/webp")


async def commit_cover_change(db: AsyncSession, storage: Storage, old_url: str, new_url: str) -> None:
    """Commit a cover change from `old_url` to `new_url` ("" = none), tidying up files either way."""
    try:
        await db.commit()
    except Exception:
        if new_url and new_url != old_url:
            await storage.delete(new_url)
        raise
    # Only remove the old file once the database points at the new one. Storage ignores
    # URLs it didn't issue, so covers that were external links are left alone.
    if old_url and old_url != new_url:
        await storage.delete(old_url)
