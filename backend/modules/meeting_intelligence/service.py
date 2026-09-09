"""
modules/meeting_intelligence/service.py

Persistence + retrieval logic for Meeting Intelligence.

Phase 3 implements meeting creation (video upload -> disk + DB row) and
deletion. Transcription / diarization / AI analysis and their orchestration
are added in later phases via pipeline.py; nothing here starts processing.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from models.meeting import Meeting
from modules.meeting_intelligence.config import meeting_settings
from modules.meeting_intelligence.processing.audio import AudioExtractionError, extract_audio
from modules.meeting_intelligence.storage import (
    EmptyUploadError,
    FileTooLargeError,
    MeetingVideoStorage,
    StorageError,
    UnsupportedMediaError,
    get_storage,
)


def create_meeting(
    db: Session,
    *,
    created_by: int,
    upload_file: UploadFile,
    title: str,
    description: str | None = None,
    meeting_date: datetime | None = None,
    storage: MeetingVideoStorage | None = None,
) -> Meeting:
    """
    Create a meeting from an uploaded video.

    Flow: insert the row (to get an id) -> stream the file to storage ->
    record the path reference -> commit. The video bytes never touch the DB.
    On any storage failure nothing is committed and no partial file remains.
    """
    storage = storage or get_storage()

    if not title or not title.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A meeting title is required.")

    meeting = Meeting(
        created_by=created_by,
        title=title.strip(),
        description=description,
        meeting_date=meeting_date,
        status="pending",
    )
    db.add(meeting)
    db.flush()  # assigns meeting.id, no commit yet
    meeting_id = meeting.id

    try:
        stored = storage.save_video(
            meeting_id,
            fileobj=upload_file.file,
            original_filename=upload_file.filename or "",
            content_type=upload_file.content_type,
        )
    except UnsupportedMediaError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc))
    except FileTooLargeError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(exc))
    except (EmptyUploadError, StorageError) as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    meeting.source_video_path     = stored.relative_path
    meeting.source_video_filename = stored.original_filename
    meeting.source_media_type     = stored.content_type
    meeting.file_size_bytes       = stored.size_bytes

    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete_meeting_files(meeting_id)
        raise
    db.refresh(meeting)
    return meeting


def get_meeting(db: Session, meeting_id: int) -> Meeting:
    """Fetch a meeting or raise 404."""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Meeting id={meeting_id} not found.")
    return meeting


def extract_meeting_audio(
    db: Session,
    meeting_id: int,
    *,
    storage: MeetingVideoStorage | None = None,
) -> Meeting:
    """
    Extract audio from a meeting's stored video and record `audio_path`
    (relative reference only — no bytes in the DB). The source video is
    preserved. Pipeline status transitions are handled by pipeline.py
    (Phase 8), not here.

    Raises HTTP 422 if the meeting has no source video, the video file is
    missing from storage, or FFmpeg fails. No partial audio file is left on
    failure.
    """
    storage = storage or get_storage()
    meeting = get_meeting(db, meeting_id)

    if not meeting.source_video_path:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Meeting has no source video to extract audio from.")

    try:
        source = storage.resolve(meeting.source_video_path)
    except StorageError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if not source.is_file():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Source video file is missing from storage.")

    target = storage.derived_target(meeting_id, meeting_settings.audio_filename)
    try:
        info = extract_audio(
            source, target,
            sample_rate=meeting_settings.audio_sample_rate,
            channels=meeting_settings.audio_channels,
        )
    except AudioExtractionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Audio extraction failed: {exc}")

    meeting.audio_path = storage.to_relative(info.path)
    if info.duration_sec:
        meeting.duration_sec = info.duration_sec
    db.commit()
    db.refresh(meeting)
    return meeting


def delete_meeting(
    db: Session,
    meeting_id: int,
    *,
    storage: MeetingVideoStorage | None = None,
) -> None:
    """Delete a meeting row (children cascade) and its stored files."""
    storage = storage or get_storage()
    meeting = get_meeting(db, meeting_id)
    db.delete(meeting)
    db.commit()
    storage.delete_meeting_files(meeting_id)
