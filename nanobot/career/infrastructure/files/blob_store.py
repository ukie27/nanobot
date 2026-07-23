"""Atomic content-addressed local blob storage."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StoredBlob:
    sha256: str
    relative_path: str
    size_bytes: int


class LocalBlobStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, content: bytes) -> StoredBlob:
        digest = hashlib.sha256(content).hexdigest()
        relative = Path(digest[:2]) / digest[2:4] / digest
        destination = self.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            handle, temporary_name = tempfile.mkstemp(prefix=".blob-", dir=destination.parent)
            temporary = Path(temporary_name)
            try:
                with os.fdopen(handle, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, destination)
            finally:
                if temporary.exists():
                    temporary.unlink()
        return StoredBlob(
            sha256=digest,
            relative_path=relative.as_posix(),
            size_bytes=len(content),
        )
