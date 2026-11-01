"""
models/escalation.py

SQLAlchemy ORM models for escalations.

`escalations` — one row per (rule, entity) that has gone unattended past
its threshold, e.g. a leave request still pending after N hours. The
unique (rule, entity_type, entity_id) constraint is what makes the sweep
idempotent: re-running it (or two workers racing) can never open a
second escalation for the same thing. It is resolved automatically once
the underlying record is dealt with.

`scheduled_job_runs` — when each periodic job last ran. This app has no
scheduler process, so the escalation sweep is triggered lazily by normal
traffic; this row (locked FOR UPDATE SKIP LOCKED) throttles it and keeps
concurrent workers from running it twice — no in-process memory needed.
"""

from sqlalchemy import (
    BigInteger, CheckConstraint, Column, DateTime, SmallInteger, String, UniqueConstraint,
)
from sqlalchemy.sql import func

from config.database import Base

ESCALATION_STATUSES = ("open", "resolved")


class Escalation(Base):
    __tablename__ = "escalations"
    __table_args__ = (
        UniqueConstraint("rule", "entity_type", "entity_id", name="uq_escalations_rule_entity"),
        CheckConstraint("status IN ('open', 'resolved')", name="chk_escalations_status"),
        CheckConstraint(
            "(status = 'open' AND resolved_at IS NULL) OR (status = 'resolved' AND resolved_at IS NOT NULL)",
            name="chk_escalations_resolved_at",
        ),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    rule = Column(String(50), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(BigInteger, nullable=False)
    status = Column(String(20), nullable=False, server_default="open", default="open", index=True)
    summary = Column(String(255), nullable=False)
    recipient_count = Column(SmallInteger, nullable=False, server_default="0", default=0)
    triggered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Escalation id={self.id} rule={self.rule!r} {self.entity_type}:{self.entity_id} {self.status}>"


class ScheduledJobRun(Base):
    __tablename__ = "scheduled_job_runs"

    job_name = Column(String(50), primary_key=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<ScheduledJobRun {self.job_name} last_run_at={self.last_run_at}>"
