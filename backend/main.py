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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
from modules.meeting_intelligence.router import router as meeting_router
from modules.recruitment.router import router as recruitment_router

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
)

# ------------------------------------------------------------------ #
# CORS middleware
# Adjust `allow_origins` in production to the exact frontend domain.
# ------------------------------------------------------------------ #
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
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
