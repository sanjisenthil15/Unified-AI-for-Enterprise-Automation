"""
models/leave_request.py

SQLAlchemy ORM model for the `leave_requests` table.

An employee asks for time off; an Admin or HR Manager approves or
rejects it. Only an approved request marks the employee's attendance
days `on_leave` (see modules/leave/service.py). There is deliberately no
leave-balance / entitlement model — this app has no approved policy for
one, so the request records the working days it covers and nothing more.
"""

from sqlalchemy import (
    BigInteger, CheckConstraint, Column, Date, DateTime, ForeignKey, Index, SmallInteger, String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from config.database import Base

# Keep in sync with chk_leave_requests_type in the leave_requests migration.
LEAVE_TYPES = ("annual", "sick", "casual", "unpaid", "other")
LEAVE_STATUSES = ("pending", "approved", "rejected", "cancelled")


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="chk_leave_requests_dates"),
        CheckConstraint(
            "leave_type IN ('annual', 'sick', 'casual', 'unpaid', 'other')",
            name="chk_leave_requests_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
            name="chk_leave_requests_status",
        ),
        CheckConstraint(
            "status NOT IN ('approved', 'rejected') OR (reviewed_by_id IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="chk_leave_requests_reviewed",
        ),
        CheckConstraint(
            "status <> 'rejected' OR length(trim(coalesce(decision_note, ''))) > 0",
            name="chk_leave_requests_rejection_reason",
        ),
        CheckConstraint(
            "status <> 'cancelled' OR cancelled_at IS NOT NULL",
            name="chk_leave_requests_cancelled_at",
        ),
        Index("ix_leave_requests_employee_dates", "employee_id", "start_date", "end_date"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    employee_id = Column(
        BigInteger,
        ForeignKey("employees.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    leave_type = Column(String(20), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    working_days = Column(SmallInteger, nullable=False)
    reason = Column(String(500), nullable=False)

    status = Column(String(20), nullable=False, server_default="pending", default="pending", index=True)
    reviewed_by_id = Column(
        BigInteger,
        ForeignKey("users.id", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=True,
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    # Required when rejecting; an optional comment when approving.
    decision_note = Column(String(500), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    employee = relationship("Employee")
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])

    def __repr__(self) -> str:
        return f"<LeaveRequest id={self.id} employee_id={self.employee_id} status={self.status!r}>"
