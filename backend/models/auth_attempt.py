"""
models/auth_attempt.py

SQLAlchemy ORM model for `auth_attempts` — the counters behind login and
registration rate limiting (core/rate_limit.py).

Only HMAC-SHA256 digests (keyed with SECRET_KEY) of the normalised email
and the client IP are stored — never the raw email, IP or any password —
so the table can't be used to enumerate who tried to sign in. Rows older
than a day are pruned as new ones are written.
"""

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, Index, String
from sqlalchemy.sql import func

from config.database import Base

AUTH_ATTEMPT_KINDS = ("login_failure", "registration")


class AuthAttempt(Base):
    __tablename__ = "auth_attempts"
    __table_args__ = (
        CheckConstraint("kind IN ('login_failure', 'registration')", name="chk_auth_attempts_kind"),
        Index("ix_auth_attempts_kind_account", "kind", "account_key", "created_at"),
        Index("ix_auth_attempts_kind_ip", "kind", "ip_key", "created_at"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    kind = Column(String(20), nullable=False)
    account_key = Column(String(64), nullable=True)
    ip_key = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
