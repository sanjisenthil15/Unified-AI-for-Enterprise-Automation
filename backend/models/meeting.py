"""
models/meeting.py

SQLAlchemy ORM model for the `meetings` table.
Used by the Meeting Intelligence module.

NOTE: This is the original single-table placeholder. It is intentionally
NOT registered in models/__init__.py yet — the Meeting Intelligence module
(feature/meeting-offline) will replace it with the full offline-processing
schema (meetings, participants, speakers, transcripts, segments, analyses,
action items) via its own Alembic migration.
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, Integer, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class Meeting(Base):
    """A recorded meeting submitted for AI transcription and summarisation."""

    __tablename__ = "meetings"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    created_by = Column(
        BigInteger,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    title        = Column(String(255),  nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    duration_sec = Column(Integer,      nullable=True)
    audio_path   = Column(String(512),  nullable=True)

    status = Column(
        Enum("pending", "transcribing", "summarizing", "completed", "failed",
             name="meeting_status"),
        nullable=False,
        default="pending",
        index=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self) -> str:
        return f"<Meeting id={self.id} status={self.status!r}>"
