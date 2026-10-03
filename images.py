import io
from collections.abc import Callable

from fastapi import UploadFile
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
MAX_FRAMES = 200
# Total pixels across all frames of a processed animation. Every resized frame is held in
# memory before encoding, so this bounds memory use for large animated uploads.
MAX_ANIMATION_PIXELS = 25_000_000

# Reject decompression bombs: a tiny file that expands to an enormous bitmap.
Image.MAX_IMAGE_PIXELS = 40_000_000


class ImageError(ValueError):
    """The upload isn't an acceptable image. The message is safe to show to the user."""


def reencode(data: bytes, resize: Callable[[Image.Image], Image.Image]) -> bytes:
    """Validate an uploaded image, apply `resize` to every frame and return it as WebP.

    Re-encoding (rather than storing the upload as-is) strips EXIF/GPS metadata and
    anything smuggled alongside the pixels, and guarantees the file really is an image.
    Blocking, so run it in a threadpool.
    """
    out = io.BytesIO()
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ALLOWED_FORMATS:
                raise ImageError("Please upload a JPEG, PNG, WebP or GIF image.")

            if getattr(image, "is_animated", False):
                # Cap frames so a small file can't make us resize thousands of images.
                if image.n_frames > MAX_FRAMES:
                    raise ImageError(f"Animated images can have at most {MAX_FRAMES} frames.")
                frames, durations, pixels = [], [], 0
                for frame in ImageSequence.Iterator(image):
                    # RGBA keeps transparency from PNG/GIF/WebP; WebP output supports alpha.
                    resized = resize(frame.convert("RGBA"))
                    pixels += resized.width * resized.height
                    if pixels > MAX_ANIMATION_PIXELS:
                        raise ImageError("That animation is too large. Try fewer frames or a smaller size.")
                    frames.append(resized)
                    # Browsers treat 0 ms GIF frames as ~100 ms; WebP would play them instantly.
                    durations.append(frame.info.get("duration") or 100)
                frames[0].save(
                    out, format="WEBP", quality=85, save_all=True, append_images=frames[1:],
                    duration=durations, loop=image.info.get("loop", 0),
                )
            else:
                resize(ImageOps.exif_transpose(image).convert("RGBA")).save(out, format="WEBP", quality=85)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise ImageError("That file isn't a valid image.") from exc
    return out.getvalue()


async def read_upload(upload: UploadFile, max_bytes: int) -> bytes:
    data = await upload.read(max_bytes + 1)
    if not data:
        raise ImageError("Please choose an image to upload.")
    if len(data) > max_bytes:
        raise ImageError(f"Images must be {max_bytes // (1024 * 1024)} MB or smaller.")
    return data


def has_file(upload: UploadFile | None) -> bool:
    # A file input left empty still submits a part, with no filename and no content.
    return upload is not None and bool(upload.filename)
