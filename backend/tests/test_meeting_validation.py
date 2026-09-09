"""
Phase 9 — validation & hardening.

Regression + hardening checks that span the whole module: error-message
sanitisation, no binary storage, storage cleanup, reprocess safety, and
graceful handling of unexpected stage failures.
"""

import io
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import inspect, text

from config.database import SessionLocal, engine
from config.settings import settings
from models.meeting import Meeting
from models.meeting_action_item import MeetingActionItem
from models.meeting_analysis import MeetingAnalysis
from models.meeting_transcript import MeetingTranscript
from modules.meeting_intelligence import pipeline as pipeline_mod
from modules.meeting_intelligence import service
from modules.meeting_intelligence.processing.analysis import AnalysisResult, ExtractedActionItem
from modules.meeting_intelligence.storage import LocalMeetingVideoStorage

REAL_MP4_HEADER = b"\x00\x00\x00\x18ftypmp42"
GARBAGE_VIDEO = b"this is absolutely not a video file " * 60
_PLACEHOLDERS = {"", "your_gemini_api_key_here", "changeme"}
HAS_GEMINI = (settings.GEMINI_API_KEY or "").strip() not in _PLACEHOLDERS


@pytest.fixture
def storage(tmp_path):
    return LocalMeetingVideoStorage(
        tmp_path / "meetings", allowed_extensions=(".mp4", ".wav"), max_bytes=50 * 1024 * 1024
    )


def _upload_file(data, name="m.mp4", ctype="video/mp4"):
    from starlette.datastructures import Headers
    from fastapi import UploadFile
    return UploadFile(file=io.BytesIO(data), filename=name, headers=Headers({"content-type": ctype}))


# --------------------------------------------------------------------------- #
# req 6 / 12 — sanitised error messages
# --------------------------------------------------------------------------- #
def test_pipeline_failure_message_has_no_paths_or_key(db, meeting_owner, storage, monkeypatch):
    monkeypatch.setattr(pipeline_mod.meeting_settings, "storage_dir", str(storage.base_dir))
    m = service.create_meeting(db, created_by=meeting_owner, upload_file=_upload_file(GARBAGE_VIDEO),
                               title="Garbage", storage=storage)
    mid = m.id
    db.commit()
    db.close()

    # real audio-extraction stage fails on the garbage file
    monkeypatch.setattr(pipeline_mod, "get_storage", lambda: storage, raising=False)
    from modules.meeting_intelligence import service as svc
    monkeypatch.setattr(svc, "get_storage", lambda: storage)
    pipeline_mod.run_meeting_pipeline(mid)

    fresh = SessionLocal()
    meeting = fresh.get(Meeting, mid)
    msg = meeting.error_message or ""
    fresh.close()

    assert meeting.status == "failed"
    assert msg
    assert "\\Users\\" not in msg and "C:\\" not in msg
    assert "source_" not in msg and str(storage.base_dir) not in msg
    key = (settings.GEMINI_API_KEY or "").strip()
    if key and key not in _PLACEHOLDERS:
        assert key not in msg


def test_scrub_redacts_key_and_paths(monkeypatch):
    monkeypatch.setattr(pipeline_mod.settings, "GEMINI_API_KEY", "AIzaSyREALKEY1234567890abcdef")
    out = pipeline_mod._scrub(
        r"boom AIzaSyREALKEY1234567890abcdef at C:\Users\bob\uploads\meetings\9\source_x.mp4 done"
    )
    assert "AIzaSyREALKEY1234567890abcdef" not in out
    assert "C:\\Users" not in out
    assert "source_x.mp4" in out  # basename kept, directory stripped


# --------------------------------------------------------------------------- #
# req 6 — no partial audio / no orphan records on failure
# --------------------------------------------------------------------------- #
def test_failure_at_audio_leaves_no_wav_and_a_failed_row(db, meeting_owner, storage, monkeypatch):
    m = service.create_meeting(db, created_by=meeting_owner, upload_file=_upload_file(GARBAGE_VIDEO),
                               title="Bad", storage=storage)
    mid = m.id
    db.commit()

    def boom_audio(_db, _mid):
        raise HTTPException(422, "Audio extraction failed: could not process the video (bad data)")

    monkeypatch.setattr(pipeline_mod, "extract_meeting_audio", boom_audio)
    pipeline_mod.run_meeting_pipeline(mid)

    db.expire_all()
    meeting = db.get(Meeting, mid)
    assert meeting.status == "failed"
    assert meeting.audio_path is None
    assert not (storage.base_dir / str(mid) / "audio.wav").exists()
    # no transcript / analysis half-written
    assert db.query(MeetingTranscript).filter_by(meeting_id=mid).count() == 0
    assert db.query(MeetingAnalysis).filter_by(meeting_id=mid).count() == 0


def test_unexpected_stage_error_marks_failed_gracefully(db, meeting_owner, storage, monkeypatch):
    m = service.create_meeting(db, created_by=meeting_owner, upload_file=_upload_file(REAL_MP4_HEADER + b"x" * 999),
                               title="Boom", storage=storage)
    mid = m.id
    db.commit()

    monkeypatch.setattr(pipeline_mod, "extract_meeting_audio", lambda d, i: None)
    monkeypatch.setattr(pipeline_mod, "transcribe_meeting",
                        lambda d, i: (_ for _ in ()).throw(RuntimeError("db connection reset")))
    pipeline_mod.run_meeting_pipeline(mid)

    db.expire_all()
    meeting = db.get(Meeting, mid)
    assert meeting.status == "failed"
    assert "transcription stage" in meeting.error_message
    assert "db connection reset" in meeting.error_message


# --------------------------------------------------------------------------- #
# req 5 — malformed AI response through the pipeline
# --------------------------------------------------------------------------- #
def test_pipeline_analysis_provider_error_marks_failed(db, meeting_owner, storage, monkeypatch):
    m = service.create_meeting(db, created_by=meeting_owner, upload_file=_upload_file(REAL_MP4_HEADER + b"x" * 999),
                               title="Analysis boom", storage=storage)
    mid = m.id
    db.add(MeetingTranscript(meeting_id=mid, full_text="Speaker 1: hi", segment_count=0))
    db.commit()

    from modules.meeting_intelligence.processing.analysis import AnalysisError, AnalysisProvider

    class BadProvider(AnalysisProvider):
        def analyze(self, text):
            raise AnalysisError("Model returned non-JSON: sorry", kind="parse")

    monkeypatch.setattr(pipeline_mod, "extract_meeting_audio", lambda d, i: None)
    monkeypatch.setattr(pipeline_mod, "transcribe_meeting", lambda d, i: None)
    monkeypatch.setattr(pipeline_mod, "diarize_meeting", lambda d, i: None)
    monkeypatch.setattr(pipeline_mod, "analyze_meeting",
                        lambda d, i: service.analyze_meeting(d, i, provider=BadProvider()))
    pipeline_mod.run_meeting_pipeline(mid)

    db.expire_all()
    meeting = db.get(Meeting, mid)
    assert meeting.status == "failed"
    assert "analysis stage" in meeting.error_message
    assert db.query(MeetingAnalysis).filter_by(meeting_id=mid).count() == 0


# --------------------------------------------------------------------------- #
# req 9 — reprocess keeps manually assigned action items
# --------------------------------------------------------------------------- #
def test_reprocess_pipeline_preserves_assigned_action_items(db, meeting_owner, storage, monkeypatch):
    m = service.create_meeting(db, created_by=meeting_owner, upload_file=_upload_file(REAL_MP4_HEADER + b"x" * 999),
                               title="Reprocess", storage=storage)
    mid = m.id
    db.add(MeetingTranscript(meeting_id=mid, full_text="Speaker 1: plan things", segment_count=0))
    db.commit()

    result_v1 = AnalysisResult(
        summary="v1 summary", key_points=["kp1"], decisions=["d1"],
        action_items=[ExtractedActionItem("Do task A", "Speaker 1", None, 0.8),
                      ExtractedActionItem("Do task B", None, None, 0.5)],
        sentiment="neutral", model_provider="fake", model_name="v1", raw_response={},
    )
    result_v2 = AnalysisResult(
        summary="v2 summary", key_points=["kp2"], decisions=[],
        action_items=[ExtractedActionItem("Do task C", None, None, 0.9)],
        sentiment="neutral", model_provider="fake", model_name="v2", raw_response={},
    )

    class P:
        def __init__(self, r): self.r = r
        def analyze(self, t): return self.r

    service.analyze_meeting(db, mid, provider=P(result_v1))
    items = db.query(MeetingActionItem).filter_by(meeting_id=mid).order_by(MeetingActionItem.id).all()
    items[0].assigned_to_user_id = meeting_owner
    items[0].assignment_method = "manual"
    items[0].description = "Do task A (edited by human)"
    db.commit()
    kept_id = items[0].id

    service.analyze_meeting(db, mid, provider=P(result_v2))
    db.expire_all()
    remaining = db.query(MeetingActionItem).filter_by(meeting_id=mid).all()
    descs = {i.description for i in remaining}
    assert "Do task A (edited by human)" in descs   # manual item survived
    assert "Do task C" in descs                     # new AI item added
    assert "Do task B" not in descs                 # untouched AI item replaced
    assert any(i.id == kept_id and i.assignment_method == "manual" for i in remaining)
    assert db.query(MeetingAnalysis).filter_by(meeting_id=mid).count() == 1


# --------------------------------------------------------------------------- #
# req 10 — PostgreSQL stores no video/audio bytes
# --------------------------------------------------------------------------- #
def test_no_binary_columns_anywhere_in_meeting_tables():
    insp = inspect(engine)
    meeting_tables = [t for t in insp.get_table_names() if t.startswith("meeting")]
    assert meeting_tables
    offenders = []
    for table in meeting_tables:
        for col in insp.get_columns(table):
            if str(col["type"]).upper() in ("BYTEA", "BLOB", "OID", "LARGE_BINARY"):
                offenders.append(f"{table}.{col['name']}")
    assert not offenders, f"binary columns found: {offenders}"


def test_path_columns_are_short_varchar():
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT column_name, data_type, character_maximum_length "
            "FROM information_schema.columns "
            "WHERE table_name = 'meetings' AND column_name IN ('source_video_path', 'audio_path')"
        )).fetchall()
    by_name = {r.column_name: r for r in rows}
    for name in ("source_video_path", "audio_path"):
        assert by_name[name].data_type == "character varying"
        assert by_name[name].character_maximum_length <= 1024


# --------------------------------------------------------------------------- #
# req 11 — local storage cleanup on delete (API level)
# --------------------------------------------------------------------------- #
def test_delete_via_api_removes_stored_files(client, new_user, monkeypatch):
    monkeypatch.setattr("modules.meeting_intelligence.router.run_meeting_pipeline", lambda mid: None)
    from modules.meeting_intelligence.router import storage_dependency
    backend = storage_dependency()

    u = new_user()
    r = client.post("/api/v1/meetings", headers=u["headers"], data={"title": "To delete"},
                    files={"file": ("clip.mp4", io.BytesIO(REAL_MP4_HEADER + b"x" * 4096), "video/mp4")})
    mid = r.json()["id"]
    assert (backend.base_dir / str(mid)).exists()

    assert client.delete(f"/api/v1/meetings/{mid}", headers=u["headers"]).status_code == 204
    assert not (backend.base_dir / str(mid)).exists()


# --------------------------------------------------------------------------- #
# req 12 — .env not tracked, no secret in the repo
# --------------------------------------------------------------------------- #
def test_env_is_git_ignored_and_untracked():
    import subprocess
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    tracked = subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True, text=True).stdout.splitlines()
    assert not any(p.endswith("/.env") or p == ".env" for p in tracked)
    assert "backend/.env.example" in tracked  # the template is tracked

    ignored = subprocess.run(["git", "check-ignore", "backend/.env"], cwd=repo, capture_output=True, text=True)
    assert ignored.returncode == 0  # .env is ignored
