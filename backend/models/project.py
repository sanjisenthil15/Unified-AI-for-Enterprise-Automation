"""
models/project.py

SQLAlchemy ORM model for the `projects` table.
Used by the Employee Management module — each project has exactly one
team lead (an Employee), and employees can be staffed on a project.
"""

from sqlalchemy import Column, Date, Integer, BigInteger, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class Project(Base):
    """A project team within the company, led by one designated employee."""

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)

    name        = Column(String(150), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    status      = Column(String(20), nullable=False, default="planning", server_default="planning")
    start_date  = Column(Date, nullable=True)
    deadline    = Column(Date, nullable=True)

    team_lead_id = Column(
        BigInteger,
        ForeignKey("employees.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    manager_user_id = Column(
        BigInteger,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    archived_at  = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    team_lead = relationship("Employee", foreign_keys=[team_lead_id])
    manager   = relationship("User", foreign_keys=[manager_user_id])
    members   = relationship("Employee", back_populates="project", foreign_keys="Employee.project_id")

    def __repr__(self) -> str:
        return f"<Project id={self.id} name={self.name!r}>"
