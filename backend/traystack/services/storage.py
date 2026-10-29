import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Protocol


class InvalidUpload(ValueError):
    pass


class UploadTooLarge(InvalidUpload):
    pass


@dataclass(frozen=True)
class StoredBlob:
    storage_key: str
    sha256: str
    size_bytes: int


class Storage(Protocol):
    def put_bytes(self, data: bytes, mime_type: str) -> StoredBlob: ...
    def put_stream(self, stream: BinaryIO, max_bytes: int) -> StoredBlob: ...
    def open(self, storage_key: str) -> BinaryIO: ...
    def path_for(self, storage_key: str) -> Path: ...
    def exists(self, storage_key: str) -> bool: ...


class LocalStorage:
    """Opaque content-addressed keys; immutable files, atomically published."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, storage_key: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}", storage_key):
            raise ValueError("Invalid storage key")
        digest = storage_key.rsplit("/", 1)[1]
        if storage_key[:5] != f"{digest[:2]}/{digest[2:4]}":
            raise ValueError("Invalid storage key")
        path = (self.root / storage_key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Storage path outside root")
        return path

    def exists(self, storage_key: str) -> bool:
        return self.path_for(storage_key).is_file()

    def open(self, storage_key: str) -> BinaryIO:
        return self.path_for(storage_key).open("rb")

    def put_bytes(self, data: bytes, mime_type: str) -> StoredBlob:
        # MIME is artifact metadata; identical bytes share a blob across representations.
        return self.put_stream(BytesIO(data), len(data))

    def put_stream(self, stream: BinaryIO, max_bytes: int) -> StoredBlob:
        digest = hashlib.sha256()
        size = 0
        # Staging on the same filesystem makes link publication atomic.
        with tempfile.NamedTemporaryFile(dir=self.root, prefix=".upload-") as staged:
            while chunk := stream.read(min(1024 * 1024, max_bytes + 1 - size)):
                size += len(chunk)
                if size > max_bytes:
                    raise UploadTooLarge("File exceeds upload size limit")
                digest.update(chunk)
                staged.write(chunk)
            if size == 0:
                raise InvalidUpload("Empty files are not supported")
            staged.flush()
            os.fsync(staged.fileno())
            sha = digest.hexdigest()
            key = f"{sha[:2]}/{sha[2:4]}/{sha}"
            target = self.path_for(key)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.link(staged.name, target)
            except FileExistsError:
                # An existing deduplicated blob must really contain these bytes.
                with target.open("rb") as existing:
                    if hashlib.file_digest(existing, "sha256").hexdigest() != sha:
                        raise OSError("Stored blob integrity check failed") from None
            return StoredBlob(key, sha, size)
