"""
models/sprint.py

SQLAlchemy ORM model for the `sprints` table.
A weekly sprint scoped to a Project, created by that project's team lead
(or admin/hr_manager).
"""

from sqlalchemy import Column, String, Date, DateTime, ForeignKey, Enum, BigInteger, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class Sprint(Base):
    """A time-boxed sprint of work for one project."""

    __tablename__ = "sprints"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    project_id = Column(
        Integer,
        ForeignKey("projects.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name = Column(String(150), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    status = Column(
        Enum("planned", "active", "completed", name="sprint_status"),
        nullable=False,
        default="planned",
        index=True,
    )

    created_by = Column(
        BigInteger,
        ForeignKey("employees.id", onupdate="CASCADE", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    project = relationship("Project")
    creator = relationship("Employee", foreign_keys=[created_by])
    tasks = relationship("SprintTask", back_populates="sprint", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Sprint id={self.id} name={self.name!r} project_id={self.project_id}>"
