"""
models/meeting_transcript_segment.py

SQLAlchemy ORM model for the `meeting_transcript_segments` table.

One row per transcribed utterance: timestamped text with the diarization
speaker attached. `speaker_label` is denormalised from `meeting_speakers`
so the transcript renders without a join.
"""

from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, BigInteger, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class MeetingTranscriptSegment(Base):
    """A single timestamped, speaker-attributed transcript segment."""

    __tablename__ = "meeting_transcript_segments"
    __table_args__ = (
        Index("ix_meeting_transcript_segments_meeting_seq", "meeting_id", "seq"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    meeting_id = Column(
        BigInteger,
        ForeignKey("meetings.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    speaker_id = Column(
        BigInteger,
        ForeignKey("meeting_speakers.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    speaker_label = Column(String(50), nullable=True,
                           comment="Denormalised from meeting_speakers.label")

    seq      = Column(Integer, nullable=False, comment="0-based order within the meeting")
    start_ms = Column(Integer, nullable=False)
    end_ms   = Column(Integer, nullable=False)
    text     = Column(Text,    nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    meeting = relationship("Meeting", back_populates="segments")
    speaker = relationship("MeetingSpeaker", back_populates="segments")

    def __repr__(self) -> str:
        return f"<MeetingTranscriptSegment id={self.id} meeting_id={self.meeting_id} seq={self.seq}>"
