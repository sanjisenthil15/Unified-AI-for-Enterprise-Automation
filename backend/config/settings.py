"""
config/settings.py
"""

import logging
import os
from typing import Optional
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Locate backend/.env file reliably regardless of working directory
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"

# Values that have appeared in this repository (old code default and the
# .env.example placeholder) — never acceptable as a signing key.
_INSECURE_SECRET_KEYS = {"", "unified_ai_enterprise_secret_key_2026", "your_jwt_secret_key_here"}


def is_hosted_environment() -> bool:
    """True on Render (which sets RENDER=true on every service) or wherever
    ENVIRONMENT=production is set explicitly."""
    return os.environ.get("RENDER", "").lower() == "true" or os.environ.get("ENVIRONMENT", "").lower() == "production"


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "mysql+pymysql://root:password@localhost:3306/enterprise_ai"

    @field_validator("DATABASE_URL")
    @classmethod
    def _use_psycopg3_driver(cls, v: str) -> str:
        """
        Managed Postgres hosts (e.g. Render) hand out a bare
        postgres:// / postgresql:// connection string. This project uses
        the psycopg3 driver (psycopg[binary] in requirements.txt, no
        psycopg2), which SQLAlchemy only picks up for the explicit
        postgresql+psycopg:// scheme — rewrite it so a pasted-in managed
        connection string works without a manual edit.

        Also strips stray leading/trailing whitespace or newlines — easy to
        pick up invisibly when copy-pasting a long connection string into a
        dashboard's env-var field, and otherwise gets sent to Postgres as
        part of the database name (e.g. "postgres\n"), which then fails
        with a confusing "database ... does not exist" error.
        """
        v = v.strip()
        if v.startswith("postgres://"):
            return "postgresql+psycopg://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            return "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    # JWT — must come from the environment. There is deliberately no usable
    # default: a key committed to the repo would let anyone forge tokens.
    SECRET_KEY: str = ""

    @field_validator("SECRET_KEY")
    @classmethod
    def _require_real_secret(cls, v: str) -> str:
        v = v.strip()
        if v in _INSECURE_SECRET_KEYS or len(v) < 16:
            message = (
                "SECRET_KEY is missing or a published placeholder. Set it in the environment "
                "(or backend/.env) to a long random value, e.g. "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
            # Hosted deployments refuse to start; local development only warns.
            if is_hosted_environment():
                raise ValueError(message)
            logging.getLogger(__name__).warning("%s (allowed only because this is not a hosted deployment)", message)
        return v

    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # AI
    GEMINI_API_KEY: str = ""

    # Application
    APP_NAME: str = "Unified AI for Enterprise Automation"
    DEBUG: bool = False

    # Dev convenience — when true, every request is treated as DEV_USER_EMAIL
    # (a seeded admin) and role checks are skipped. NEVER enable in production.
    AUTH_DISABLED: bool = False
    DEV_USER_EMAIL: str = "demo@demo.com"

    # Public self-registration (POST /auth/register). Unset = allowed for
    # local development, refused on hosted deployments, where accounts are
    # provisioned by Admin / HR through Employee Management. Set explicitly
    # to override either way (opening it in production is a business call).
    ALLOW_PUBLIC_REGISTRATION: Optional[bool] = None

    @property
    def public_registration_enabled(self) -> bool:
        if self.ALLOW_PUBLIC_REGISTRATION is not None:
            return self.ALLOW_PUBLIC_REGISTRATION
        return not is_hosted_environment()

    # Login / registration abuse protection (database-backed, so limits hold
    # across workers and instances). Failures are counted per account+IP,
    # per account, and per IP within a sliding window; only keyed hashes of
    # the email and IP are stored, never the raw values or any password.
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 900
    LOGIN_MAX_FAILURES_PER_ACCOUNT_IP: int = 5
    LOGIN_MAX_FAILURES_PER_ACCOUNT: int = 20
    LOGIN_MAX_FAILURES_PER_IP: int = 50
    REGISTRATION_MAX_PER_IP: int = 10
    # Behind Render's proxy the client address is in X-Forwarded-For;
    # unset = trust it only on hosted deployments.
    TRUST_PROXY_HEADERS: Optional[bool] = None

    @field_validator("AUTH_DISABLED")
    @classmethod
    def _never_disable_auth_when_hosted(cls, v: bool) -> bool:
        if v and is_hosted_environment():
            raise ValueError("AUTH_DISABLED=true is refused on a hosted deployment — it makes every visitor an admin.")
        return v

    # Comma-separated list of allowed frontend origins (browser CORS +
    # the Online Meeting WebSocket's Origin check share this one setting).
    # Add the deployed frontend's URL alongside localhost when hosting.
    CORS_ORIGINS: str = "http://localhost:3000"

    # Permanent file storage (core/object_storage.py). "local" keeps files on
    # this machine's disk — fine for development, NOT permanent on Render.
    # "supabase" uses private Supabase Storage buckets; the service-role key
    # stays on the server and is never sent to browsers.
    STORAGE_BACKEND: str = "local"
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    STORAGE_BUCKET_MEETINGS: str = "meeting-recordings"
    STORAGE_BUCKET_RESUMES: str = "recruitment-resumes"
    SIGNED_URL_TTL_SECONDS: int = 300

    @field_validator("STORAGE_BACKEND")
    @classmethod
    def _known_storage_backend(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("local", "supabase"):
            raise ValueError("STORAGE_BACKEND must be 'local' or 'supabase'.")
        if v == "local" and is_hosted_environment():
            logging.getLogger(__name__).warning(
                "STORAGE_BACKEND=local on a hosted deployment: uploaded files are lost on every restart."
            )
        return v

    @field_validator("SUPABASE_SERVICE_ROLE_KEY")
    @classmethod
    def _supabase_configured(cls, v: str, info) -> str:
        if info.data.get("STORAGE_BACKEND") == "supabase" and (not v.strip() or not info.data.get("SUPABASE_URL", "").strip()):
            raise ValueError("STORAGE_BACKEND=supabase needs SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return v.strip()

    # Escalations (Phase 4.4 / 5.3). The sweep runs at most once per
    # ESCALATION_SWEEP_INTERVAL_SECONDS across all workers (throttled and
    # locked through the scheduled_job_runs table). It is triggered by the
    # in-process scheduler (modules/escalations/scheduler.py) and, as a
    # backstop, by notification polling. ESCALATION_AUTO_SWEEP switches off
    # both automatic triggers; the Admin "Run check now" button still works.
    ESCALATION_AUTO_SWEEP: bool = True
    ESCALATION_SCHEDULER_ENABLED: bool = True
    ESCALATION_SCHEDULER_INTERVAL_SECONDS: int = 300
    ESCALATION_SWEEP_INTERVAL_SECONDS: int = 300
    LEAVE_PENDING_ESCALATION_HOURS: int = 48
    ACTION_ITEM_REVIEW_ESCALATION_HOURS: int = 72

    # SMTP / Email configuration for interview invitations & notifications
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "recruitment@enterprise.ai"
    SMTP_FROM_NAME: str = "EnterpriseAI HR Recruitment Team"
    SMTP_USE_TLS: bool = True

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
        # Other modules (e.g. modules/meeting_intelligence/config.py) read
        # module-prefixed keys (MEETING_*) from this same shared .env file.
        # Without "ignore", pydantic-settings forbids unknown keys and crashes
        # the whole app at import time as soon as any such key is uncommented.
        extra="ignore",
    )


settings = Settings()