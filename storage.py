from pathlib import Path, PurePosixPath
from typing import Protocol

import anyio

from config import settings


class Storage(Protocol):
    """Where uploaded files live. Implement this for S3 etc. and return it from get_storage()."""

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


_storage: Storage = LocalStorage(settings.media_root, settings.media_url)


def get_storage() -> Storage:
    return _storage
