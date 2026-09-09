"""
models/meeting_transcript.py

SQLAlchemy ORM model for the `meeting_transcripts` table.

One row per meeting: the full plain-text transcript plus transcription
metadata. The diarized, timestamped breakdown lives in
`meeting_transcript_segments`.
"""

from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class MeetingTranscript(Base):
    """Full-text transcript for a meeting (1:1 with `meetings`)."""

    __tablename__ = "meeting_transcripts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    meeting_id = Column(
        BigInteger,
        ForeignKey("meetings.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    full_text     = Column(Text,        nullable=False)
    language      = Column(String(16),  nullable=True)
    whisper_model = Column(String(50),  nullable=True)
    word_count    = Column(Integer,     nullable=True)
    segment_count = Column(Integer,     nullable=True)

    transcribed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    meeting = relationship("Meeting", back_populates="transcript")

    def __repr__(self) -> str:
        return f"<MeetingTranscript id={self.id} meeting_id={self.meeting_id} words={self.word_count}>"
