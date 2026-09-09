"""
Phase 3 — video upload + local storage.

Storage-layer unit tests (temp dir) + create_meeting service integration
tests (real PostgreSQL, temp storage dir).
"""

import io

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from sqlalchemy import text

from models.meeting import Meeting
from modules.meeting_intelligence import service
from modules.meeting_intelligence.storage import (
    EmptyUploadError,
    FileTooLargeError,
    LocalMeetingVideoStorage,
    StorageError,
    StoredFileNotFoundError,
    UnsupportedMediaError,
)

FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x11" * 4096
ALLOWED = (".mp4", ".mov", ".mkv", ".webm", ".m4a", ".wav")


@pytest.fixture
def storage(tmp_path):
    return LocalMeetingVideoStorage(
        tmp_path / "meetings", allowed_extensions=ALLOWED, max_bytes=10 * 1024 * 1024
    )


def _upload(data: bytes, name: str, ctype: str = "video/mp4") -> UploadFile:
    return UploadFile(
        file=io.BytesIO(data),
        filename=name,
        headers=Headers({"content-type": ctype}),
    )


# --------------------------------------------------------------------------- #
# Storage layer
# --------------------------------------------------------------------------- #
def test_save_video_success(storage):
    stored = storage.save_video(42, fileobj=io.BytesIO(FAKE_MP4),
                                original_filename="Team Sync.mp4", content_type="video/mp4")
    assert stored.size_bytes == len(FAKE_MP4)
    assert stored.relative_path.startswith("42/source_")
    assert stored.relative_path.endswith(".mp4")
    assert stored.absolute_path.is_file()
    assert stored.absolute_path.read_bytes() == FAKE_MP4
    # stored name is generated, not the client's
    assert "Team Sync" not in stored.relative_path


@pytest.mark.parametrize("name", ["notes.txt", "malware.exe", "clip", "video.mp4.exe"])
def test_reject_invalid_extension(storage, name):
    with pytest.raises(UnsupportedMediaError):
        storage.save_video(1, fileobj=io.BytesIO(FAKE_MP4), original_filename=name)
    assert not (storage.base_dir / "1").exists() or not any((storage.base_dir / "1").iterdir())


def test_reject_oversize(tmp_path):
    tiny = LocalMeetingVideoStorage(tmp_path, allowed_extensions=ALLOWED, max_bytes=1024)
    with pytest.raises(FileTooLargeError):
        tiny.save_video(1, fileobj=io.BytesIO(b"x" * 5000), original_filename="big.mp4")
    # partial file cleaned up
    assert not list((tmp_path / "1").glob("*")) if (tmp_path / "1").exists() else True


def test_reject_empty_upload(storage):
    with pytest.raises(EmptyUploadError):
        storage.save_video(1, fileobj=io.BytesIO(b""), original_filename="empty.mp4")


def test_unique_filenames_no_overwrite(storage):
    a = storage.save_video(7, fileobj=io.BytesIO(FAKE_MP4), original_filename="call.mp4")
    b = storage.save_video(7, fileobj=io.BytesIO(FAKE_MP4 + b"zzz"), original_filename="call.mp4")
    assert a.relative_path != b.relative_path
    assert a.absolute_path.is_file() and b.absolute_path.is_file()
    assert a.absolute_path.read_bytes() != b.absolute_path.read_bytes()
    assert len(list((storage.base_dir / "7").glob("source_*"))) == 2


def test_resolve_rejects_path_escape(storage):
    with pytest.raises(StorageError):
        storage.resolve("../../../etc/passwd")


def test_open_missing_file_raises(storage):
    with pytest.raises(StoredFileNotFoundError):
        storage.open_video("999/source_deadbeef.mp4")
    assert storage.exists("999/source_deadbeef.mp4") is False


def test_delete_meeting_files_idempotent(storage):
    stored = storage.save_video(5, fileobj=io.BytesIO(FAKE_MP4), original_filename="x.mp4")
    assert stored.absolute_path.is_file()
    storage.delete_meeting_files(5)
    assert not (storage.base_dir / "5").exists()
    storage.delete_meeting_files(5)  # no error second time


# --------------------------------------------------------------------------- #
# create_meeting service (DB + disk)
# --------------------------------------------------------------------------- #
def test_create_meeting_persists_path_only(db, meeting_owner, storage):
    up = _upload(FAKE_MP4, "Quarterly Review.mp4")
    meeting = service.create_meeting(
        db, created_by=meeting_owner, upload_file=up, title="Quarterly Review",
        storage=storage,
    )
    mid = meeting.id
    assert meeting.status == "pending"
    assert meeting.file_size_bytes == len(FAKE_MP4)
    assert meeting.source_video_filename == "Quarterly Review.mp4"

    # reload from a fresh query — path persisted
    db.expire_all()
    row = db.get(Meeting, mid)
    assert row.source_video_path.startswith(f"{mid}/source_")
    assert storage.resolve(row.source_video_path).read_bytes() == FAKE_MP4


def test_create_meeting_stores_no_blob(db, meeting_owner, storage):
    up = _upload(FAKE_MP4, "call.mp4")
    meeting = service.create_meeting(
        db, created_by=meeting_owner, upload_file=up, title="Call", storage=storage
    )
    raw = db.execute(
        text("SELECT source_video_path, pg_column_size(source_video_path) AS sz "
             "FROM meetings WHERE id = :i"),
        {"i": meeting.id},
    ).one()
    assert isinstance(raw.source_video_path, str)
    assert raw.sz < 200                     # a path, not a video
    assert len(raw.source_video_path) < 120


def test_create_meeting_rejects_invalid_type_and_rolls_back(db, meeting_owner, storage):
    before = db.query(Meeting).filter(Meeting.created_by == meeting_owner).count()
    up = _upload(b"plain text", "agenda.txt", ctype="text/plain")
    with pytest.raises(HTTPException) as ei:
        service.create_meeting(
            db, created_by=meeting_owner, upload_file=up, title="Bad", storage=storage
        )
    assert ei.value.status_code == 415
    db.rollback()
    after = db.query(Meeting).filter(Meeting.created_by == meeting_owner).count()
    assert after == before                  # nothing committed
    assert not (storage.base_dir).exists() or not list(storage.base_dir.rglob("source_*"))


def test_delete_meeting_removes_row_and_files(db, meeting_owner, storage):
    up = _upload(FAKE_MP4, "gone.mp4")
    meeting = service.create_meeting(
        db, created_by=meeting_owner, upload_file=up, title="Gone", storage=storage
    )
    mid = meeting.id
    rel = meeting.source_video_path
    service.delete_meeting(db, mid, storage=storage)
    assert db.get(Meeting, mid) is None
    assert storage.exists(rel) is False
