"""
modules/meeting_intelligence/schemas.py

Pydantic request/response schemas for the Meeting Intelligence API.

Internal storage details (source_video_path, audio_path, raw provider
payloads) are deliberately NOT exposed.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Meetings
# --------------------------------------------------------------------------- #
class MeetingCreate(BaseModel):
    """Multipart form fields that accompany the uploaded video file."""
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=4000)
    meeting_date: datetime | None = None
    project_id: int | None = Field(None, description="Which project this meeting was about, if any")


class MeetingResponse(BaseModel):
    id: int
    title: str
    description: str | None = None
    project_id: int | None = None
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
# Scheduling
# --------------------------------------------------------------------------- #
class ScheduleMeetingCreate(BaseModel):
    """Books a future meeting for a project team. Every current member of
    that project (plus the organizer) is invited and notified; starting an
    Online Meeting against this booking later fills in the same record with
    a transcript, AI analysis and action items — same as an uploaded
    recording."""
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=4000)
    project_id: int = Field(..., description="Which project team to invite")
    scheduled_at: datetime


class ScheduledMeetingOut(BaseModel):
    id: int
    title: str
    description: str | None = None
    project_id: int
    project_name: str
    organizer_user_id: int
    organizer_name: str
    scheduled_at: datetime
    invitee_count: int
    created_at: datetime


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
    final_description: Optional[str] = None
    assignee_name_raw: Optional[str] = None
    assigned_to_user_id: Optional[int] = None
    assigned_to_employee_id: Optional[int] = None
    assignment_method: str
    due_date: Optional[date] = None
    priority: Optional[str] = None
    status: str
    review_status: str = "proposed"
    reviewed_by_id: Optional[int] = None
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    is_legacy_conversion: bool = False
    source: str
    ai_confidence: Optional[float] = None
    converted_sprint_task_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AssignActionItem(BaseModel):
    assigned_to_user_id: int | None = Field(
        None, description="User id to assign this action item to; null to unassign.",
    )


class ConfirmActionItem(BaseModel):
    assignee_id: int = Field(..., description="Employee id to assign the action item to")
    due_date: date = Field(..., description="Mandatory deadline for confirmed action item")
    final_description: Optional[str] = Field(None, description="Optional human-edited description")


class RejectActionItem(BaseModel):
    rejection_reason: str = Field(..., min_length=1, description="Mandatory non-empty reason for rejecting")


class ConvertActionItemReq(BaseModel):
    sprint_id: int = Field(..., description="Sprint id belonging to the meeting's project")


class ConvertActionItem(BaseModel):
    sprint_id: int = Field(..., description="Sprint id belonging to the meeting's project")
    assignee_id: Optional[int] = Field(None, description="Optional override assignee id")
    due_date: Optional[date] = Field(None, description="Optional override due date")
