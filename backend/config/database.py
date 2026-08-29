"""
config/database.py

SQLAlchemy engine, session factory, and declarative base.

Usage in FastAPI routes:
    from config.database import get_db
    db: Session = Depends(get_db)
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config.settings import settings


# ------------------------------------------------------------------ #
# Engine — pool_pre_ping keeps connections healthy across restarts
# ------------------------------------------------------------------ #
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,   # recycle connections every 30 minutes
    echo=settings.DEBUG, # log SQL statements only in debug mode
)

# ------------------------------------------------------------------ #
# Session factory — autocommit/autoflush disabled for explicit control
# ------------------------------------------------------------------ #
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ------------------------------------------------------------------ #
# Declarative base — all ORM models inherit from this
# ------------------------------------------------------------------ #
class Base(DeclarativeBase):
    """
    Shared SQLAlchemy declarative base.
    Every ORM model must inherit from Base so that
    Base.metadata.create_all() creates all tables together.
    """
    pass


# ------------------------------------------------------------------ #
# FastAPI dependency — yields a DB session per request
# ------------------------------------------------------------------ #
def get_db():
    """
    Yields a SQLAlchemy session and ensures it is closed after each request,
    even if an exception occurs.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
