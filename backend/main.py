"""
main.py

Entry point for the Unified AI for Enterprise Automation FastAPI application.

Responsibilities:
  - Create the FastAPI application instance
  - Register all module routers under the /api/v1 prefix
  - Configure CORS middleware
  - Register global exception handlers

Database schema is managed by Alembic. Run `alembic upgrade head` from the
backend/ directory before starting the server.

To run the server:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.database import SessionLocal
from config.settings import settings

# ------------------------------------------------------------------ #
# Import the models package so SQLAlchemy mappers are registered when
# the app starts (also keeps model import errors visible at boot).
# ------------------------------------------------------------------ #
import models  # noqa: F401

# ------------------------------------------------------------------ #
# Module routers — import and register each router here as modules
# are implemented. Only the auth router is active at this stage.
# ------------------------------------------------------------------ #
from auth.router import router as auth_router
from modules.meeting_intelligence import service as meeting_service
from modules.meeting_intelligence.router import router as meeting_router
from modules.meeting_online.router import router as online_meeting_router
from modules.recruitment.router import router as recruitment_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A meeting stuck in "pending"/"processing" only means the previous
    # process died mid-run (that background task can't survive a restart) —
    # recover it to "failed" so "Retry processing" can pick it back up,
    # instead of leaving it stranded forever. This is a best-effort cleanup,
    # not a requirement to serve traffic — a DB hiccup here must never stop
    # the whole app from starting.
    try:
        db = SessionLocal()
        try:
            meeting_service.recover_orphaned_meetings(db)
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).warning("Startup meeting recovery skipped", exc_info=True)
    yield


# ------------------------------------------------------------------ #
# Application instance
# ------------------------------------------------------------------ #
app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description=(
        "Unified AI for Enterprise Automation — "
        "a modular enterprise platform with a shared AI Decision Engine."
    ),
    docs_url="/docs",       # Swagger UI
    redoc_url="/redoc",     # ReDoc UI
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ------------------------------------------------------------------ #
# CORS middleware
# Allowed origins come from settings.CORS_ORIGINS (comma-separated) —
# defaults to the React dev server; add the deployed frontend URL there.
# ------------------------------------------------------------------ #
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------ #
# Register routers
# All API routes are versioned under /api/v1
# ------------------------------------------------------------------ #
API_PREFIX = "/api/v1"

app.include_router(auth_router,        prefix=API_PREFIX)
app.include_router(recruitment_router, prefix=API_PREFIX)
# Static /meetings/online routes precede offline /meetings/{meeting_id}.
app.include_router(online_meeting_router, prefix=API_PREFIX)
app.include_router(meeting_router,     prefix=API_PREFIX)
# Future modules will be registered here, for example:
# app.include_router(employee_router,  prefix=API_PREFIX)
# app.include_router(incident_router,  prefix=API_PREFIX)
# app.include_router(analytics_router, prefix=API_PREFIX)
# app.include_router(support_router,   prefix=API_PREFIX)

# ------------------------------------------------------------------ #
# Database schema is managed by Alembic, NOT by Base.metadata.create_all().
# Apply migrations before starting the server:
#     cd backend && alembic upgrade head
# ------------------------------------------------------------------ #


# ------------------------------------------------------------------ #
# Health check — useful for load balancers and container orchestrators
# ------------------------------------------------------------------ #
@app.get("/health", tags=["Health"], summary="API health check")
def health_check() -> dict:
    """Returns a simple alive signal. No auth required."""
    return {"status": "ok", "app": settings.APP_NAME}
