"""
modules/meeting_intelligence/schemas.py

Pydantic request/response schemas for the Meeting Intelligence API.

Internal storage details (source_video_path, audio_path, raw provider
payloads) are deliberately NOT exposed.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Meetings
# --------------------------------------------------------------------------- #
class MeetingCreate(BaseModel):
    """Multipart form fields that accompany the uploaded video file."""
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=4000)
    meeting_date: datetime | None = None


class MeetingResponse(BaseModel):
    id: int
    title: str
    description: str | None = None
    status: str
    error_message: str | None = None
    source_video_filename: str | None = None
    source_media_type: str | None = None
    file_size_bytes: int | None = None
    duration_sec: int | None = None
    language: str | None = None
    meeting_date: datetime | None = None
    processing_started_at: datetime | None = None
    processing_finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MeetingListItem(BaseModel):
    id: int
    title: str
    status: str
    duration_sec: int | None = None
    meeting_date: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# --------------------------------------------------------------------------- #
# Speakers
# --------------------------------------------------------------------------- #
class SpeakerOut(BaseModel):
    id: int
    label: str
    display_name: str | None = None
    mapped_user_id: int | None = None
    mapped_employee_id: int | None = None
    segment_count: int | None = None
    total_speaking_sec: int | None = None

    model_config = {"from_attributes": True}


# --------------------------------------------------------------------------- #
# Transcript
# --------------------------------------------------------------------------- #
class TranscriptSegmentOut(BaseModel):
    seq: int
    start_ms: int
    end_ms: int
    speaker_id: int | None = None
    speaker_label: str | None = None
    text: str

    model_config = {"from_attributes": True}


class TranscriptResponse(BaseModel):
    meeting_id: int
    language: str | None = None
    whisper_model: str | None = None
    word_count: int | None = None
    segment_count: int | None = None
    full_text: str
    speakers: list[SpeakerOut] = []
    segments: list[TranscriptSegmentOut] = []


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
class AnalysisResponse(BaseModel):
    meeting_id: int
    summary: str
    key_points: list[str] = []
    decisions: list[str] = []
    sentiment: str | None = None
    model_provider: str
    model_name: str | None = None
    generated_at: datetime

    model_config = {"from_attributes": True, "protected_namespaces": ()}


# --------------------------------------------------------------------------- #
# Action items
# --------------------------------------------------------------------------- #
class ActionItemOut(BaseModel):
    id: int
    description: str
    assignee_name_raw: str | None = None
    assigned_to_user_id: int | None = None
    assigned_to_employee_id: int | None = None
    assignment_method: str
    due_date: date | None = None
    priority: str | None = None
    status: str
    source: str
    ai_confidence: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AssignActionItem(BaseModel):
    assigned_to_user_id: int | None = Field(
        None, description="User id to assign this action item to; null to unassign.",
    )
