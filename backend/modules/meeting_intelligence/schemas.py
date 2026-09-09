"""
modules/meeting_intelligence/schemas.py

Pydantic response schemas for the Meeting Intelligence API.

Phase 3 defines the meeting representation. Note that `source_video_path`
(the internal disk reference) is deliberately NOT exposed. Transcript /
analysis / action-item schemas are added in Phase 8.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MeetingResponse(BaseModel):
    id: int
    title: str
    description: str | None = None
    status: str
    source_video_filename: str | None = None
    source_media_type: str | None = None
    file_size_bytes: int | None = None
    duration_sec: int | None = None
    meeting_date: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
