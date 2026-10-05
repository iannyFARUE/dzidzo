import logging
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Protocol

import anyio
import boto3
from botocore.exceptions import BotoCoreError, ClientError

from config import settings

logger = logging.getLogger(__name__)


class Storage(Protocol):
    """Where uploaded files live. get_storage() returns the backend chosen in settings."""

    async def save(self, key: str, data: bytes, content_type: str) -> str:
        """Store `data` under `key` and return the public URL."""
        ...

    async def delete(self, url: str) -> None:
        """Remove the file behind `url`. URLs this backend didn't issue are ignored."""
        ...


class LocalStorage:
    def __init__(self, root: str, url_prefix: str) -> None:
        self.root = Path(root).resolve()
        self.url_prefix = url_prefix.rstrip("/")

    def _path_for(self, key: str) -> Path:
        path = (self.root / PurePosixPath(key)).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"key escapes storage root: {key!r}")
        return path

    async def save(self, key: str, data: bytes, content_type: str) -> str:
        path = anyio.Path(self._path_for(key))
        await path.parent.mkdir(parents=True, exist_ok=True)
        await path.write_bytes(data)
        return f"{self.url_prefix}/{key}"

    async def delete(self, url: str) -> None:
        prefix = f"{self.url_prefix}/"
        if not url.startswith(prefix):
            return
        try:
            path = self._path_for(url.removeprefix(prefix))
        except ValueError:
            return
        await anyio.Path(path).unlink(missing_ok=True)


class S3Storage:
    # Every key is a fresh random name that's never overwritten, so browsers and CDNs
    # can cache files for good.
    CACHE_CONTROL = "public, max-age=31536000, immutable"

    def __init__(
        self,
        bucket: str,
        region: str,
        *,
        access_key_id: str = "",
        secret_access_key: str = "",
        public_url: str = "",
        endpoint_url: str = "",
    ) -> None:
        self.bucket = bucket
        # boto3 clients are thread-safe, so one is shared by all the worker threads below.
        self.client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url or None,
            # None falls back to boto3's credential chain (env vars, ~/.aws, IAM role).
            aws_access_key_id=access_key_id or None,
            aws_secret_access_key=secret_access_key or None,
        )
        if not public_url:
            public_url = (
                f"{endpoint_url.rstrip('/')}/{bucket}" if endpoint_url
                else f"https://{bucket}.s3.{region}.amazonaws.com"
            )
        self.url_prefix = public_url.rstrip("/")

    async def save(self, key: str, data: bytes, content_type: str) -> str:
        # boto3 is blocking, so run it in a worker thread to keep the event loop free.
        await anyio.to_thread.run_sync(partial(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            CacheControl=self.CACHE_CONTROL,
        ))
        return f"{self.url_prefix}/{key}"

    async def delete(self, url: str) -> None:
        prefix = f"{self.url_prefix}/"
        if not url.startswith(prefix):
            return
        try:
            await anyio.to_thread.run_sync(partial(
                self.client.delete_object, Bucket=self.bucket, Key=url.removeprefix(prefix)
            ))
        except (BotoCoreError, ClientError):
            # Deletes happen after the database already points at the new file, so a
            # failure only leaves an orphaned object behind; don't fail the request.
            logger.exception("failed to delete %s from S3", url)


def _make_storage() -> Storage:
    if settings.storage_backend == "s3":
        return S3Storage(
            settings.s3_bucket,
            settings.s3_region,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key.get_secret_value(),
            public_url=settings.s3_public_url,
            endpoint_url=settings.s3_endpoint_url,
        )
    return LocalStorage(settings.media_root, settings.media_url)


_storage: Storage = _make_storage()


def get_storage() -> Storage:
    return _storage
