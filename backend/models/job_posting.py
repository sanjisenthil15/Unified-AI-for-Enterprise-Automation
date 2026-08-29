"""
models/job_posting.py

SQLAlchemy ORM model for the `job_postings` table.
A job posting defines what HR is looking for; resumes are matched against it.
"""

from sqlalchemy import Column, String, Text, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class JobPosting(Base):
    """
    Represents a single job opening created by an HR user.
    All uploaded resumes are linked to exactly one job posting.
    """

    __tablename__ = "job_postings"

    id = Column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)

    # HR user who created this posting (FK → users.id)
    created_by = Column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    title = Column(String(150), nullable=False, comment="Job title, e.g. 'Python Backend Developer'")
    description = Column(Text, nullable=True, comment="Full job description")
    required_skills = Column(Text, nullable=False, comment="Comma-separated required skills")
    min_education = Column(
        String(100),
        nullable=False,
        default="Bachelor's Degree",
        comment="Minimum education level required",
    )
    experience_level = Column(
        Enum("entry", "junior", "mid", "senior", "lead"),
        nullable=False,
        default="mid",
        comment="Seniority level — entry/junior means fresher-friendly scoring applies",
    )
    status = Column(
        Enum("draft", "active", "closed"),
        nullable=False,
        default="active",
        index=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # One job posting has many resumes
    resumes = relationship("Resume", back_populates="job_posting", lazy="dynamic")

    def __repr__(self) -> str:
        return f"<JobPosting id={self.id} title={self.title!r}>"
