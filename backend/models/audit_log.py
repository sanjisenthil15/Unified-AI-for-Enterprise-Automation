"""
models/audit_log.py

SQLAlchemy ORM model for the append-only `audit_logs` table.

Rows are written inside the same transaction as the change they
describe (core/audit.py), so a rolled-back change leaves no audit row.
A database trigger rejects UPDATE, DELETE and TRUNCATE, so not even the
application itself can rewrite history. actor_user_id deliberately has
no foreign key — the trail must outlive the user it names. Passwords,
password hashes, tokens and free-text personal notes are never stored
(see core/audit.py for the per-model column allow-lists).
"""

from sqlalchemy import BigInteger, Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.types import JSON

from config.database import Base

# JSONB on Postgres, plain JSON elsewhere (sqlite-backed unit tests).
_JSON = JSON().with_variant(JSONB(), "postgresql")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_entity", "entity_type", "entity_id"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    actor_user_id = Column(BigInteger, nullable=True, index=True)
    actor_role = Column(String(50), nullable=True)
    action = Column(String(80), nullable=False, index=True)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(64), nullable=True)
    before = Column(_JSON, nullable=True)
    after = Column(_JSON, nullable=True)
    correlation_id = Column(String(64), nullable=True, index=True)

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} action={self.action!r} {self.entity_type}:{self.entity_id}>"
