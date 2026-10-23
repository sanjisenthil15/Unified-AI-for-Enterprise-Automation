"""
models/attendance.py

SQLAlchemy ORM model for the `attendance_records` table.
One row per employee per calendar day — daily check-in/check-out.
"""

from sqlalchemy import Column, String, Date, DateTime, ForeignKey, Enum, BigInteger, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base


class Attendance(Base):
    """An employee's check-in/check-out record for a single calendar day."""

    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_attendance_employee_date"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    employee_id = Column(
        BigInteger,
        ForeignKey("employees.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    work_date = Column(Date, nullable=False, index=True)
    check_in_at = Column(DateTime(timezone=True), nullable=True)
    check_out_at = Column(DateTime(timezone=True), nullable=True)

    status = Column(
        Enum("present", "late", "absent", "on_leave", name="attendance_status"),
        nullable=False,
        default="present",
        index=True,
    )
    notes = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    employee = relationship("Employee")

    def __repr__(self) -> str:
        return f"<Attendance employee_id={self.employee_id} date={self.work_date} status={self.status!r}>"
