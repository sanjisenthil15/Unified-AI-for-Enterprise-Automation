"""
models/department.py

SQLAlchemy ORM model for the `departments` table.
Used by the Employee Management module.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class Department(Base):
    """An organizational department that employees belong to."""

    __tablename__ = "departments"

    id = Column(Integer, primary_key=True, autoincrement=True)

    name        = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    employees = relationship("Employee", back_populates="department")

    def __repr__(self) -> str:
        return f"<Department id={self.id} name={self.name!r}>"
