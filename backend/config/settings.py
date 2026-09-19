"""
config/settings.py
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Locate backend/.env file reliably regardless of working directory
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "mysql+pymysql://root:password@localhost:3306/enterprise_ai"

    # JWT
    SECRET_KEY: str = "unified_ai_enterprise_secret_key_2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # AI
    GEMINI_API_KEY: str = ""

    # Application
    APP_NAME: str = "Unified AI for Enterprise Automation"
    DEBUG: bool = False

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )


settings = Settings()