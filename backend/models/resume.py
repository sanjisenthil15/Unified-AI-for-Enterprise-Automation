"""
models/resume.py

SQLAlchemy ORM model for the `resumes` table.
Stores the uploaded PDF path, extracted raw text, and (later) AI analysis results.
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum, Float
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class Resume(Base):
    """
    Represents one uploaded resume tied to a job posting.
    Phase 1: stores file path and extracted text.
    Phase 2+: stores AI score, summary, recommendation.
    """

    __tablename__ = "resumes"

    id = Column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)

    # Which job posting this resume belongs to
    job_posting_id = Column(
        BIGINT(unsigned=True),
        ForeignKey("job_postings.id", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Candidate identity
    candidate_name  = Column(String(120), nullable=False)
    candidate_email = Column(String(255), nullable=True, index=True)

    # File storage
    file_name   = Column(String(255), nullable=False, comment="Original uploaded filename")
    file_path   = Column(String(512), nullable=False, comment="Path where the PDF is saved on disk")

    # Phase 1 — raw extracted text from the PDF
    extracted_text = Column(Text, nullable=True, comment="Plain text extracted from the PDF by PyPDF2")

    # Phase 2 — AI analysis fields (NULL until Gemini integration)
    ai_score        = Column(Float,      nullable=True, comment="Weighted match score 0-100")
    ai_summary      = Column(Text,       nullable=True, comment="Gemini-generated candidate summary")
    strengths       = Column(Text,       nullable=True, comment="JSON list of identified strengths")
    missing_skills  = Column(Text,       nullable=True, comment="JSON list of skills gaps")
    recommendation  = Column(
        Enum("selected", "hold", "rejected"),
        nullable=True,
        comment="AI recommendation — HR makes the final decision",
    )

    # Processing state
    status = Column(
        Enum("uploaded", "extracted", "analysed", "error"),
        nullable=False,
        default="uploaded",
        index=True,
        comment="Tracks which pipeline stage this resume is in",
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationship back to job posting
    job_posting = relationship("JobPosting", back_populates="resumes")

    def __repr__(self) -> str:
        return f"<Resume id={self.id} name={self.candidate_name!r} status={self.status!r}>"
