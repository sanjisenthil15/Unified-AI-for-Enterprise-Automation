"""
config/settings.py
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str

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

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )


settings = Settings()