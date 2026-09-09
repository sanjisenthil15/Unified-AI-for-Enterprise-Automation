"""
models/employee.py

SQLAlchemy ORM model for the `employees` table.
Used by the Employee Management module.
"""

from sqlalchemy import Column, String, Date, DateTime, ForeignKey, Enum, BigInteger, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class Employee(Base):
    """An employee record linked to a User account."""

    __tablename__ = "employees"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    user_id = Column(
        BigInteger,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
        index=True,
    )
    # department_id is nullable until the departments table is active
    department_id = Column(Integer, nullable=True, index=True)

    employee_code   = Column(String(30),  nullable=False, unique=True)
    job_title       = Column(String(100), nullable=False)
    phone           = Column(String(30),  nullable=True)
    hire_date       = Column(Date,        nullable=False)

    employment_type = Column(
        Enum("full_time", "part_time", "contract", "intern",
             name="employee_employment_type"),
        nullable=False,
        default="full_time",
    )
    status = Column(
        Enum("active", "inactive", "on_leave", "terminated",
             name="employee_status"),
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
    deleted_at = Column(DateTime(timezone=True), nullable=True, default=None)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return f"<Employee id={self.id} code={self.employee_code!r} status={self.status!r}>"
