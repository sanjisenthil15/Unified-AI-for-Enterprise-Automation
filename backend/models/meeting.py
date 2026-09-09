"""
models/meeting.py

SQLAlchemy ORM model for the `meetings` table — the root entity of the
Meeting Intelligence module (offline processing pipeline).

The uploaded video is stored on local disk (see
modules/meeting_intelligence/storage.py). PostgreSQL keeps only the path
reference in `source_video_path` — never the media blob itself.
"""

from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, Enum, Integer, BigInteger,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base

# Pipeline states — see modules/meeting_intelligence/pipeline.py
MEETING_STATUSES = (
    "pending",
    "extracting_audio",
    "transcribing",
    "diarizing",
    "analyzing",
    "completed",
    "failed",
)


class Meeting(Base):
    """A recorded meeting submitted for offline transcription and analysis."""

    __tablename__ = "meetings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Uploader / owner of this meeting record.
    created_by = Column(
        BigInteger,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # --- meeting metadata ------------------------------------------------- #
    title        = Column(String(255), nullable=False)
    description  = Column(Text,         nullable=True)
    meeting_date = Column(DateTime(timezone=True), nullable=True,
                          comment="When the meeting actually took place")

    # --- source media (stored on disk; DB holds the reference only) ------ #
    source_video_path     = Column(String(1024), nullable=True,
                                   comment="Local filesystem path to the uploaded video")
    source_video_filename = Column(String(512),  nullable=True,
                                   comment="Original upload filename")
    source_media_type     = Column(String(100),  nullable=True,
                                   comment="Detected MIME / container type")
    file_size_bytes       = Column(BigInteger,   nullable=True)

    # --- derived artefacts (also on disk) ------------------------------- #
    audio_path    = Column(String(1024), nullable=True,
                           comment="Extracted 16 kHz mono WAV path")
    duration_sec  = Column(Integer,      nullable=True)
    language      = Column(String(16),   nullable=True, comment="Detected/forced language code")

    # --- processing state --------------------------------------------- #
    status = Column(
        Enum(*MEETING_STATUSES, name="meeting_status"),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
    )
    error_message          = Column(Text, nullable=True)
    processing_started_at  = Column(DateTime(timezone=True), nullable=True)
    processing_finished_at = Column(DateTime(timezone=True), nullable=True)
    whisper_model          = Column(String(50), nullable=True)
    diarization_backend    = Column(String(50), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # --- relationships -------------------------------------------------- #
    creator = relationship("User", foreign_keys=[created_by])

    participants = relationship(
        "MeetingParticipant", back_populates="meeting",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    speakers = relationship(
        "MeetingSpeaker", back_populates="meeting",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    transcript = relationship(
        "MeetingTranscript", back_populates="meeting", uselist=False,
        cascade="all, delete-orphan", passive_deletes=True,
    )
    segments = relationship(
        "MeetingTranscriptSegment", back_populates="meeting",
        cascade="all, delete-orphan", passive_deletes=True,
        order_by="MeetingTranscriptSegment.seq",
    )
    analysis = relationship(
        "MeetingAnalysis", back_populates="meeting", uselist=False,
        cascade="all, delete-orphan", passive_deletes=True,
    )
    action_items = relationship(
        "MeetingActionItem", back_populates="meeting",
        cascade="all, delete-orphan", passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Meeting id={self.id} status={self.status!r} title={self.title!r}>"
