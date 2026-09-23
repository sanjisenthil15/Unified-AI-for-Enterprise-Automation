"""Online meeting contracts. These are Pydantic objects, never database tables."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


def now() -> datetime:
    return datetime.now(timezone.utc)


class StartMeeting(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=255)
    request_id: UUID


class TranscriptSegment(BaseModel):
    id: str
    speaker: str
    text: str
    start_ms: int
    end_ms: int
    source: Literal["manual", "audio"]


class ActionItemResult(BaseModel):
    description: str
    assignee: str | None = None
    priority: str | None = None
    confidence: float | None = None


class LiveAnalysisResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    summary: str
    key_points: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    action_items: list[ActionItemResult] = Field(default_factory=list)
    model_provider: str = ""
    model_name: str = ""
    transcript_count: int = 0
    generated_at: datetime = Field(default_factory=now)


class Participant(BaseModel):
    client_id: str
    speaker: str
    connected: bool = False


class OnlineMeetingSession(BaseModel):
    id: str
    title: str
    status: Literal["active", "ending", "ended"] = "active"
    started_at: datetime = Field(default_factory=now)
    ended_at: datetime | None = None
    participants: list[Participant] = Field(default_factory=list)
    transcript: list[TranscriptSegment] = Field(default_factory=list)
    analysis: LiveAnalysisResult | None = None
    analysis_status: Literal["idle", "processing", "ready", "error"] = "idle"
    analysis_error: str | None = None
    websocket_path: str


class ClientEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    type: Literal["join", "leave", "transcript", "audio", "analyze", "ping"]
    client_id: UUID | None = None
    message_id: UUID | None = None
    text: str | None = Field(default=None, min_length=1, max_length=4000)
    data: str | None = Field(default=None, min_length=1, max_length=2_800_000)
    mime_type: Literal["audio/webm", "audio/ogg", "audio/mp4", "audio/wav"] | None = None
    start_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    end_ms: int | None = Field(default=None, ge=0, le=86_400_000)

    @model_validator(mode="after")
    def validate_event(self):
        if self.type == "join" and self.client_id is None:
            raise ValueError("join requires client_id")
        if self.type in ("audio", "transcript"):
            if self.message_id is None or self.start_ms is None or self.end_ms is None:
                raise ValueError("input requires message_id, start_ms and end_ms")
            if self.end_ms < self.start_ms or self.end_ms - self.start_ms > 30_000:
                raise ValueError("input duration must be between zero and 30 seconds")
            if self.type == "transcript" and not self.text:
                raise ValueError("transcript requires nonempty text")
            if self.type == "audio" and (not self.data or not self.mime_type):
                raise ValueError("audio requires nonempty base64 data and mime_type")
        return self