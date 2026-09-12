"""Object store for original files and figure/chart images.

InMemoryObjectStore is the dependency-free default (bytes kept in a dict, returned
by ref). A LocalFsObjectStore writes under a directory. The production MinIO/S3
backend (semantica object store) is added with the real deployment; the
``ObjectStore`` protocol keeps the ingestion pipeline unaware of which is active.
"""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Protocol


class ObjectStore(Protocol):
    def put(self, data: bytes, *, suffix: str = "") -> str:
        """Store bytes; return a stable ref (e.g. 'obj://<hash>.png')."""
        ...

    def get(self, ref: str) -> bytes | None: ...


class InMemoryObjectStore:
    def __init__(self) -> None:
        self._blobs: dict[str, bytes] = {}

    def put(self, data: bytes, *, suffix: str = "") -> str:
        digest = hashlib.sha256(data).hexdigest()[:16]
        ref = f"obj://{digest}{suffix}"
        self._blobs[ref] = data
        return ref

    def get(self, ref: str) -> bytes | None:
        return self._blobs.get(ref)

    def __len__(self) -> int:
        return len(self._blobs)


class LocalFsObjectStore:
    def __init__(self, root: str) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes, *, suffix: str = "") -> str:
        digest = hashlib.sha256(data).hexdigest()[:16]
        name = f"{digest}{suffix}"
        (self._root / name).write_bytes(data)
        return f"file://{(self._root / name)}"

    def get(self, ref: str) -> bytes | None:
        path = Path(ref.removeprefix("file://"))
        return path.read_bytes() if path.exists() else None


def decode_b64(data_b64: str) -> bytes:
    return base64.b64decode(data_b64)
