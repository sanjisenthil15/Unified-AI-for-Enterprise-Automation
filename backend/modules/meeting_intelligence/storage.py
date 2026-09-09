"""
modules/meeting_intelligence/storage.py

Local filesystem storage for meeting media.

Design goals
    - The uploaded video lives ONLY on disk. PostgreSQL stores a relative
      path reference (meetings.source_video_path), never the bytes.
    - Stored filenames are generated (UUID) — a client filename can never
      overwrite an existing file.
    - The concrete backend sits behind the `MeetingVideoStorage` interface
      so it can be swapped for S3 / GCS / Azure Blob later without touching
      the service or pipeline. `get_storage()` is the single entry point.

Layout (base dir = backend/uploads/meetings/, git-ignored):
    <meeting_id>/source_<uuid><ext>     original upload
    <meeting_id>/audio.wav             extracted audio (added in Phase 4)

`source_video_path` stored in the DB is the backend-relative key, e.g.
    "42/source_9f8c1e2b7a044d5e8b3c1f6a2d9e4c07.mp4"
"""

from __future__ import annotations

import shutil
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable

from modules.meeting_intelligence.config import meeting_settings

_READ_CHUNK = 1024 * 1024  # 1 MiB


# --------------------------------------------------------------------------- #
# Errors — framework-agnostic on purpose (no fastapi import here)
# --------------------------------------------------------------------------- #
class StorageError(Exception):
    """Base class for storage failures."""


class UnsupportedMediaError(StorageError):
    """The upload's extension is not an accepted video/audio type."""


class FileTooLargeError(StorageError):
    """The upload exceeds the configured size limit."""


class EmptyUploadError(StorageError):
    """The upload contained no bytes."""


class StoredFileNotFoundError(StorageError, FileNotFoundError):
    """A referenced stored file does not exist on the backend."""


@dataclass(frozen=True)
class StoredVideo:
    """Result of persisting an upload. `relative_path` goes in the DB."""
    relative_path: str
    absolute_path: Path
    original_filename: str
    size_bytes: int
    content_type: str | None


# --------------------------------------------------------------------------- #
# Interface
# --------------------------------------------------------------------------- #
class MeetingVideoStorage(ABC):
    """Swap-in point for a cloud/object-storage backend later."""

    @abstractmethod
    def save_video(
        self,
        meeting_id: int,
        *,
        fileobj: BinaryIO,
        original_filename: str,
        content_type: str | None = None,
    ) -> StoredVideo:
        ...

    @abstractmethod
    def resolve(self, relative_path: str) -> Path:
        """Map a stored relative path to an absolute location (no existence check)."""

    @abstractmethod
    def open_video(self, relative_path: str) -> BinaryIO:
        """Open a stored file for reading, or raise StoredFileNotFoundError."""

    @abstractmethod
    def exists(self, relative_path: str) -> bool:
        ...

    @abstractmethod
    def derived_target(self, meeting_id: int, filename: str) -> Path:
        """
        Absolute path a processing step should WRITE a derived artefact to
        (e.g. the extracted audio). The parent directory is created.

        A cloud backend would return a temp path here and upload it on
        `to_relative()` / a dedicated save call.
        """

    @abstractmethod
    def to_relative(self, absolute_path: Path | str) -> str:
        """Map an absolute path under the backend root back to a stored key."""

    @abstractmethod
    def delete_meeting_files(self, meeting_id: int) -> None:
        """Remove every file for a meeting. Idempotent — missing is not an error."""


# --------------------------------------------------------------------------- #
# Local filesystem implementation
# --------------------------------------------------------------------------- #
class LocalMeetingVideoStorage(MeetingVideoStorage):
    def __init__(
        self,
        base_dir: Path | str,
        *,
        allowed_extensions: Iterable[str],
        max_bytes: int,
    ) -> None:
        self.base_dir = Path(base_dir).resolve()
        self.allowed_extensions = {e.lower() for e in allowed_extensions}
        self.max_bytes = int(max_bytes)

    # -- helpers ---------------------------------------------------------- #
    def _meeting_dir(self, meeting_id: int) -> Path:
        return self.base_dir / str(int(meeting_id))

    @staticmethod
    def _ext(filename: str) -> str:
        return Path(filename or "").suffix.lower()

    # -- interface ------------------------------------------------------ #
    def save_video(
        self,
        meeting_id: int,
        *,
        fileobj: BinaryIO,
        original_filename: str,
        content_type: str | None = None,
    ) -> StoredVideo:
        ext = self._ext(original_filename)
        if ext not in self.allowed_extensions:
            raise UnsupportedMediaError(
                f"Unsupported file type '{ext or '(none)'}'. "
                f"Allowed: {', '.join(sorted(self.allowed_extensions))}"
            )

        mdir = self._meeting_dir(meeting_id)
        mdir.mkdir(parents=True, exist_ok=True)

        stored_name = f"source_{uuid.uuid4().hex}{ext}"
        abs_path = mdir / stored_name

        size = 0
        try:
            with open(abs_path, "wb") as out:
                while True:
                    chunk = fileobj.read(_READ_CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise FileTooLargeError(
                            f"Upload exceeds the {self.max_bytes // (1024 * 1024)} MB limit."
                        )
                    out.write(chunk)
        except BaseException:
            abs_path.unlink(missing_ok=True)
            raise

        if size == 0:
            abs_path.unlink(missing_ok=True)
            raise EmptyUploadError("The uploaded file is empty.")

        return StoredVideo(
            relative_path=abs_path.relative_to(self.base_dir).as_posix(),
            absolute_path=abs_path,
            original_filename=original_filename,
            size_bytes=size,
            content_type=content_type,
        )

    def resolve(self, relative_path: str) -> Path:
        candidate = (self.base_dir / relative_path).resolve()
        if candidate != self.base_dir and self.base_dir not in candidate.parents:
            raise StorageError(f"Path escapes the storage root: {relative_path!r}")
        return candidate

    def open_video(self, relative_path: str) -> BinaryIO:
        path = self.resolve(relative_path)
        if not path.is_file():
            raise StoredFileNotFoundError(str(path))
        return open(path, "rb")

    def exists(self, relative_path: str) -> bool:
        try:
            return self.resolve(relative_path).is_file()
        except StorageError:
            return False

    def derived_target(self, meeting_id: int, filename: str) -> Path:
        mdir = self._meeting_dir(meeting_id)
        mdir.mkdir(parents=True, exist_ok=True)
        return mdir / filename

    def to_relative(self, absolute_path: Path | str) -> str:
        p = Path(absolute_path).resolve()
        if p != self.base_dir and self.base_dir not in p.parents:
            raise StorageError(f"Path is outside the storage root: {absolute_path!r}")
        return p.relative_to(self.base_dir).as_posix()

    def delete_meeting_files(self, meeting_id: int) -> None:
        mdir = self._meeting_dir(meeting_id)
        if mdir.exists():
            shutil.rmtree(mdir, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
_default_storage: MeetingVideoStorage | None = None


def get_storage() -> MeetingVideoStorage:
    """Return the process-wide storage backend (local filesystem for now)."""
    global _default_storage
    if _default_storage is None:
        _default_storage = LocalMeetingVideoStorage(
            meeting_settings.storage_path,
            allowed_extensions=meeting_settings.allowed_video_extensions,
            max_bytes=meeting_settings.max_upload_mb * 1024 * 1024,
        )
    return _default_storage
