"""
models/meeting_speaker.py

SQLAlchemy ORM model for the `meeting_speakers` table.

A speaker is a diarization-detected voice within one meeting. Labels stay
generic ("Speaker 1", "Speaker 2", ...) and are NOT assumed to be real
employees. The optional `mapped_user_id` / `mapped_employee_id` columns let
the UI later attach a real identity without touching transcript rows.
"""

from sqlalchemy import (
    Column, String, Integer, DateTime, ForeignKey, BigInteger, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class MeetingSpeaker(Base):
    """A distinct voice detected by speaker diarization for one meeting."""

    __tablename__ = "meeting_speakers"
    __table_args__ = (
        UniqueConstraint("meeting_id", "label", name="uq_meeting_speaker_label"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    meeting_id = Column(
        BigInteger,
        ForeignKey("meetings.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    label        = Column(String(50),  nullable=False, comment='Generic label, e.g. "Speaker 1"')
    display_name = Column(String(255), nullable=True,  comment="Editable friendly name set in the UI")

    # Optional mapping to a real identity (filled later, never assumed).
    mapped_user_id = Column(
        BigInteger,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    mapped_employee_id = Column(
        BigInteger,
        ForeignKey("employees.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    total_speaking_sec = Column(Integer, nullable=True)
    segment_count      = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # --- relationships -------------------------------------------------- #
    meeting         = relationship("Meeting", back_populates="speakers")
    mapped_user     = relationship("User",     foreign_keys=[mapped_user_id])
    mapped_employee = relationship("Employee", foreign_keys=[mapped_employee_id])
    segments = relationship(
        "MeetingTranscriptSegment", back_populates="speaker", passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<MeetingSpeaker id={self.id} meeting_id={self.meeting_id} label={self.label!r}>"
