"""
models/candidate.py

SQLAlchemy ORM model for the `candidates` table.
Used by the Recruitment AI module.
"""

from sqlalchemy import Column, String, DateTime, Enum, Integer, Numeric, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class Candidate(Base):
    """A job applicant linked to a job posting."""

    __tablename__ = "candidates"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # job_postings table will be created later; use plain FK string to avoid
    # circular import issues — SQLAlchemy resolves it at mapper configure time.
    job_posting_id = Column(
        Integer,
        nullable=True,
        index=True,
        comment="References job_postings.id — nullable until job postings module is active",
    )

    full_name    = Column(String(120), nullable=False)
    email        = Column(String(255), nullable=False, index=True)
    phone        = Column(String(30),  nullable=True)
    resume_path  = Column(String(512), nullable=True)
    linkedin_url = Column(String(512), nullable=True)
    ai_score     = Column(Numeric(5, 2), nullable=True)

    status = Column(
        Enum("applied", "screening", "interview", "offer", "hired", "rejected",
             name="candidate_status"),
        nullable=False,
        default="applied",
        index=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Candidate id={self.id} email={self.email!r} status={self.status!r}>"
