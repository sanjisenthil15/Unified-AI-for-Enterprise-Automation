"""
Phase 4 — audio extraction (imageio-ffmpeg).

processing/audio.py unit tests + extract_meeting_audio service tests
(real PostgreSQL, temp storage dir).
"""

import io
import subprocess

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from sqlalchemy import text

from models.meeting import Meeting
from modules.meeting_intelligence import service
from modules.meeting_intelligence.processing.audio import (
    AudioExtractionError,
    extract_audio,
    get_ffmpeg_exe,
)
from modules.meeting_intelligence.storage import LocalMeetingVideoStorage

ALLOWED = (".mp4", ".mov", ".mkv", ".webm", ".wav")


@pytest.fixture(scope="session")
def sample_video_bytes(tmp_path_factory) -> bytes:
    """A real 2-second MP4 (video + 440 Hz tone) built with the bundled FFmpeg."""
    d = tmp_path_factory.mktemp("sample")
    out = d / "sample.mp4"
    proc = subprocess.run(
        [
            get_ffmpeg_exe(), "-y",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=64x64:rate=10",
            "-shortest", "-c:v", "mpeg4", "-c:a", "aac", str(out),
        ],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0 and out.is_file(), proc.stderr
    return out.read_bytes()


@pytest.fixture
def storage(tmp_path):
    return LocalMeetingVideoStorage(
        tmp_path / "meetings", allowed_extensions=ALLOWED, max_bytes=50 * 1024 * 1024
    )


def _upload(data: bytes, name: str, ctype: str = "video/mp4") -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=name,
                      headers=Headers({"content-type": ctype}))


# --------------------------------------------------------------------------- #
# processing/audio.py
# --------------------------------------------------------------------------- #
def test_extract_audio_success(tmp_path, sample_video_bytes):
    src = tmp_path / "in.mp4"
    src.write_bytes(sample_video_bytes)
    out = tmp_path / "sub" / "audio.wav"

    info = extract_audio(src, out, sample_rate=16_000, channels=1)

    assert out.is_file() and info.path == out
    assert info.sample_rate == 16_000 and info.channels == 1
    assert info.duration_sec == 2
    assert info.size_bytes > 44
    assert src.read_bytes() == sample_video_bytes          # req 7: source preserved


def test_extract_audio_missing_source(tmp_path):
    with pytest.raises(AudioExtractionError):
        extract_audio(tmp_path / "nope.mp4", tmp_path / "a.wav")
    assert not (tmp_path / "a.wav").exists()


def test_extract_audio_invalid_source_cleans_up(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(b"this is not a media file")
    out = tmp_path / "a.wav"
    with pytest.raises(AudioExtractionError):
        extract_audio(bad, out)
    assert not out.exists()                                 # req 8: partial cleanup
    assert bad.read_bytes() == b"this is not a media file"  # source untouched


def test_extract_audio_removes_stale_target(tmp_path, sample_video_bytes):
    src = tmp_path / "in.mp4"
    src.write_bytes(sample_video_bytes)
    out = tmp_path / "audio.wav"
    out.write_bytes(b"stale contents")
    info = extract_audio(src, out)
    assert info.size_bytes > 100 and out.read_bytes() != b"stale contents"


# --------------------------------------------------------------------------- #
# extract_meeting_audio service (DB + disk)
# --------------------------------------------------------------------------- #
@pytest.fixture
def meeting_with_video(db, meeting_owner, storage, sample_video_bytes):
    up = _upload(sample_video_bytes, "Weekly Sync.mp4")
    m = service.create_meeting(db, created_by=meeting_owner, upload_file=up,
                               title="Weekly Sync", storage=storage)
    return m


def test_extract_meeting_audio_persists_relative_path(db, storage, meeting_with_video):
    m = service.extract_meeting_audio(db, meeting_with_video.id, storage=storage)
    mid = m.id

    assert m.audio_path == f"{mid}/audio.wav"
    assert m.duration_sec == 2
    assert storage.resolve(m.audio_path).is_file()
    # original video still present
    assert storage.exists(m.source_video_path)

    db.expire_all()
    row = db.get(Meeting, mid)
    assert row.audio_path == f"{mid}/audio.wav"


def test_extract_meeting_audio_no_blob_in_db(db, storage, meeting_with_video):
    m = service.extract_meeting_audio(db, meeting_with_video.id, storage=storage)
    raw = db.execute(
        text("SELECT audio_path, pg_column_size(audio_path) AS sz FROM meetings WHERE id = :i"),
        {"i": m.id},
    ).one()
    assert isinstance(raw.audio_path, str) and raw.sz < 100


def test_extract_meeting_audio_missing_source_file(db, storage, meeting_with_video):
    # remove the stored video, then try to extract
    storage.resolve(meeting_with_video.source_video_path).unlink()
    with pytest.raises(HTTPException) as ei:
        service.extract_meeting_audio(db, meeting_with_video.id, storage=storage)
    assert ei.value.status_code == 422
    db.expire_all()
    assert db.get(Meeting, meeting_with_video.id).audio_path is None


def test_extract_meeting_audio_no_source_video(db, meeting_owner, storage):
    m = Meeting(created_by=meeting_owner, title="Empty", status="pending")
    db.add(m)
    db.commit()
    with pytest.raises(HTTPException) as ei:
        service.extract_meeting_audio(db, m.id, storage=storage)
    assert ei.value.status_code == 422


def test_extract_meeting_audio_failure_leaves_no_partial(db, meeting_owner, storage):
    # a .mp4 whose bytes are garbage -> ffmpeg fails
    up = _upload(b"not really an mp4 file, just text" * 40, "broken.mp4")
    m = service.create_meeting(db, created_by=meeting_owner, upload_file=up,
                               title="Broken", storage=storage)
    with pytest.raises(HTTPException) as ei:
        service.extract_meeting_audio(db, m.id, storage=storage)
    assert ei.value.status_code == 422
    assert not storage.exists(f"{m.id}/audio.wav")          # req 8
    db.expire_all()
    assert db.get(Meeting, m.id).audio_path is None
    assert storage.exists(m.source_video_path)              # req 7: video preserved
