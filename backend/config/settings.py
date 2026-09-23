"""
config/settings.py
"""

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

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
        """
        if v.startswith("postgres://"):
            return "postgresql+psycopg://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            return "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    # JWT
    SECRET_KEY: str = "change-me-in-production"
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

    # Comma-separated list of allowed frontend origins (browser CORS +
    # the Online Meeting WebSocket's Origin check share this one setting).
    # Add the deployed frontend's URL alongside localhost when hosting.
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        # Other modules (e.g. modules/meeting_intelligence/config.py) read
        # module-prefixed keys (MEETING_*) from this same shared .env file.
        # Without "ignore", pydantic-settings forbids unknown keys and crashes
        # the whole app at import time as soon as any such key is uncommented.
        extra="ignore",
    )


settings = Settings()