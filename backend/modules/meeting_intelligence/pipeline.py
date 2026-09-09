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

import re
from datetime import datetime, timezone
from pathlib import Path

from config.database import SessionLocal
from config.settings import settings
from models.meeting import Meeting
from modules.meeting_intelligence.config import meeting_settings
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


_PLACEHOLDER_KEYS = {"", "your_gemini_api_key_here", "changeme"}
_WIN_ABS_PATH = re.compile(r"[A-Za-z]:\\[^\s'\"]+")


def _scrub(message: str) -> str:
    """
    Sanitise a message before it is stored / returned:
      - remove the configured Gemini API key
      - collapse internal filesystem paths to a bare name
    """
    message = str(message or "")

    key = (settings.GEMINI_API_KEY or "").strip()
    if key and len(key) >= 12 and key not in _PLACEHOLDER_KEYS:
        message = message.replace(key, "***")

    try:
        root = str(meeting_settings.storage_path)
        for variant in {root, root.replace("\\", "/")}:
            if variant:
                message = message.replace(variant, "<storage>")
    except Exception:
        pass
    message = _WIN_ABS_PATH.sub(lambda m: Path(m.group(0)).name, message)

    return message.strip()[:1000]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _mark_failed(db, meeting_id: int, message: str) -> None:
    db.rollback()
    meeting = db.get(Meeting, meeting_id)
    if meeting is None:
        return
    meeting.status = "failed"
    meeting.error_message = _scrub(message)
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
                _mark_failed(db, meeting_id, f"{stage_name} stage — {detail}")
                return

        meeting = db.get(Meeting, meeting_id)
        if meeting is not None:
            meeting.status = "completed"
            meeting.processing_finished_at = _now()
            db.commit()
    except Exception as exc:  # noqa: BLE001 — last-resort guard
        try:
            _mark_failed(db, meeting_id, f"pipeline error: {exc}")
        except Exception:
            pass
    finally:
        db.close()
