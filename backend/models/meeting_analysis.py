"""
models/meeting_analysis.py

SQLAlchemy ORM model for the `meeting_analyses` table.

One row per meeting holding the structured AI output: summary, key discussion
points, and decisions. Action items are stored as their own rows in
`meeting_action_items` (so they can be assigned and tracked).

`raw_response` keeps the full provider payload for audit / reprocessing.
"""

from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, BigInteger, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class MeetingAnalysis(Base):
    """Structured AI analysis of a meeting transcript (1:1 with `meetings`)."""

    __tablename__ = "meeting_analyses"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    meeting_id = Column(
        BigInteger,
        ForeignKey("meetings.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    summary    = Column(Text, nullable=False)
    key_points = Column(JSON, nullable=True, comment='List of strings: ["point", ...]')
    decisions  = Column(JSON, nullable=True, comment='List of strings: ["decision", ...]')
    sentiment  = Column(String(20), nullable=True)

    # Provider abstraction — "gemini" now, others possible later.
    model_provider = Column(String(50),  nullable=False, server_default="gemini")
    model_name     = Column(String(100), nullable=True)
    raw_response   = Column(JSON,        nullable=True, comment="Full provider payload for audit")
    prompt_tokens  = Column(Integer,     nullable=True)

    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    meeting      = relationship("Meeting", back_populates="analysis")
    action_items = relationship("MeetingActionItem", back_populates="analysis")

    def __repr__(self) -> str:
        return f"<MeetingAnalysis id={self.id} meeting_id={self.meeting_id}>"
