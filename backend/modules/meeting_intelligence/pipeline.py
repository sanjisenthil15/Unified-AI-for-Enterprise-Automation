"""
modules/meeting_intelligence/pipeline.py — Phase 8.

Runs the offline processing stages in order, reusing the Phase 4-7 services:

    audio extraction -> faster-whisper transcription -> speaker diarization
    -> Gemini analysis

Status transitions:
    pending -> processing -> completed
    pending / processing -> failed   (with meetings.error_message)

Executed via FastAPI BackgroundTasks (see router.py) — no Celery/Redis. The
background task owns its own DB session; it must not reuse the request's.
"""

from __future__ import annotations

from datetime import datetime, timezone

from config.database import SessionLocal
from config.settings import settings
from models.meeting import Meeting
from modules.meeting_intelligence.service import (
    analyze_meeting,
    diarize_meeting,
    extract_meeting_audio,
    transcribe_meeting,
)

def _stages():
    # Built per call so tests can monkeypatch the stage functions on this module.
    return (
        ("audio extraction", extract_meeting_audio),
        ("transcription", transcribe_meeting),
        ("speaker diarization", diarize_meeting),
        ("analysis", analyze_meeting),
    )


def _scrub(message: str) -> str:
    """Never let a configured secret appear in a stored error message."""
    key = (settings.GEMINI_API_KEY or "").strip()
    if key and len(key) >= 8 and key not in {"your_gemini_api_key_here", "changeme"}:
        message = message.replace(key, "***")
    return message[:2000]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mark_failed(db, meeting_id: int, stage: str, detail: str) -> None:
    db.rollback()
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        return
    meeting.status = "failed"
    meeting.error_message = _scrub(f"{stage} failed: {detail}")
    meeting.processing_finished_at = _now()
    db.commit()


def run_meeting_pipeline(meeting_id: int) -> None:
    """Process one meeting end to end. Safe to call from a background task."""
    db = SessionLocal()
    try:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            return
        meeting.status = "processing"
        meeting.processing_started_at = _now()
        meeting.processing_finished_at = None
        meeting.error_message = None
        db.commit()

        for stage_name, stage_fn in _stages():
            try:
                stage_fn(db, meeting_id)
            except Exception as exc:  # noqa: BLE001
                detail = getattr(exc, "detail", None) or str(exc)
                _mark_failed(db, meeting_id, stage_name, str(detail))
                return

        meeting = db.get(Meeting, meeting_id)
        if meeting is not None:
            meeting.status = "completed"
            meeting.processing_finished_at = _now()
            db.commit()
    except Exception as exc:  # noqa: BLE001 — last-resort guard
        try:
            _mark_failed(db, meeting_id, "pipeline", str(exc))
        except Exception:
            pass
    finally:
        db.close()
