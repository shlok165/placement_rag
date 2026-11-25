"""Raw file storage behind a small interface, so object storage can replace the local volume."""

import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings

_KEY = re.compile(r"^[a-z]+/[0-9a-f]{32}\.[a-z]{3,4}$")


class Storage(Protocol):
    def save(self, area: str, data: bytes, extension: str) -> str: ...

    def read(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, key: str) -> Path:
        if not _KEY.match(key):
            raise ValueError("Invalid storage key")
        return self._root / key

    def save(self, area: str, data: bytes, extension: str) -> str:
        # Names are generated, so a client-supplied file name can never reach the disk.
        key = f"{area}/{uuid.uuid4().hex}.{extension}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


@lru_cache
def get_storage() -> Storage:
    return LocalStorage(get_settings().raw_files_dir)
