"""
core/rate_limit.py

Database-backed rate limiting for login and self-registration.

Why the database: the app may run several workers / instances that share
no memory, and adding Redis would be new infrastructure. Postgres is
already shared by all of them, so a count over `auth_attempts` gives the
same answer everywhere.

Login: failed attempts are counted in a sliding window three ways —
  account + IP   (LOGIN_MAX_FAILURES_PER_ACCOUNT_IP, the normal case)
  account        (LOGIN_MAX_FAILURES_PER_ACCOUNT, distributed guessing)
  IP             (LOGIN_MAX_FAILURES_PER_IP, one source spraying accounts)
so an attacker hammering one account from elsewhere doesn't lock its
owner out until the much higher per-account ceiling, and every lock
expires by itself when the window slides. A successful login clears that
account+IP's failures. While limited, even a correct password gets 429
(checking it would turn the limit into a free password oracle).

The count-then-insert isn't atomic, so a burst of parallel requests can
overshoot a limit by roughly the burst size — acceptable for throttling.

Privacy: only HMAC-SHA256(SECRET_KEY, value) digests are stored.
"""

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from config.settings import is_hosted_environment, settings
from models.auth_attempt import AuthAttempt

REGISTRATION_WINDOW_SECONDS = 3600
RETENTION = timedelta(days=1)


def _digest(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return hmac.new(settings.SECRET_KEY.encode(), value.strip().lower().encode(), hashlib.sha256).hexdigest()


def client_ip(request: Request) -> str:
    """The caller's IP. Behind Render's proxy chain the socket peer is the
    proxy, so the client comes from X-Forwarded-For. The first entry is
    used: later entries can be intermediate proxies (e.g. a CDN edge) that
    many users share, which would put everyone in one IP bucket. A client
    could spoof the first entry, but that only lets it dodge the per-IP
    bucket — the per-account limits never depend on the IP."""
    trust = settings.TRUST_PROXY_HEADERS if settings.TRUST_PROXY_HEADERS is not None else is_hosted_environment()
    if trust:
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            return hops[0][:64]
    return request.client.host if request.client else "unknown"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _count(db: Session, kind: str, since: datetime, *, account_key=None, ip_key=None):
    query = db.query(func.count(AuthAttempt.id), func.min(AuthAttempt.created_at)).filter(
        AuthAttempt.kind == kind, AuthAttempt.created_at >= since,
    )
    if account_key is not None:
        query = query.filter(AuthAttempt.account_key == account_key)
    if ip_key is not None:
        query = query.filter(AuthAttempt.ip_key == ip_key)
    return query.one()


def _too_many(retry_after: float, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=message,
        headers={"Retry-After": str(max(1, int(retry_after) + 1))},
    )


def check_login_allowed(db: Session, email: str, ip: str) -> None:
    window = settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS
    since = _now() - timedelta(seconds=window)
    account_key, ip_key = _digest(email), _digest(ip)
    buckets = (
        ({"account_key": account_key, "ip_key": ip_key}, settings.LOGIN_MAX_FAILURES_PER_ACCOUNT_IP),
        ({"account_key": account_key}, settings.LOGIN_MAX_FAILURES_PER_ACCOUNT),
        ({"ip_key": ip_key}, settings.LOGIN_MAX_FAILURES_PER_IP),
    )
    for keys, limit in buckets:
        count, oldest = _count(db, "login_failure", since, **keys)
        if count >= limit:
            retry_after = window - (_now() - oldest).total_seconds() if oldest else window
            raise _too_many(retry_after, "Too many failed sign-in attempts. Please wait a few minutes and try again.")


def record_login_failure(db: Session, email: str, ip: str) -> None:
    """Queue a failure row; written with the caller's commit."""
    db.add(AuthAttempt(kind="login_failure", account_key=_digest(email), ip_key=_digest(ip)))
    _prune(db)


def clear_login_failures(db: Session, email: str, ip: str) -> None:
    db.query(AuthAttempt).filter(
        AuthAttempt.kind == "login_failure",
        AuthAttempt.account_key == _digest(email),
        AuthAttempt.ip_key == _digest(ip),
    ).delete(synchronize_session=False)


def check_registration_allowed(db: Session, ip: str) -> None:
    since = _now() - timedelta(seconds=REGISTRATION_WINDOW_SECONDS)
    count, oldest = _count(db, "registration", since, ip_key=_digest(ip))
    if count >= settings.REGISTRATION_MAX_PER_IP:
        retry_after = REGISTRATION_WINDOW_SECONDS - (_now() - oldest).total_seconds() if oldest else REGISTRATION_WINDOW_SECONDS
        raise _too_many(retry_after, "Too many accounts created from this network. Please try again later.")


def record_registration(db: Session, ip: str) -> None:
    db.add(AuthAttempt(kind="registration", ip_key=_digest(ip)))
    _prune(db)


def _prune(db: Session) -> None:
    db.query(AuthAttempt).filter(AuthAttempt.created_at < _now() - RETENTION).delete(synchronize_session=False)
