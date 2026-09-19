"""
main.py

Entry point for the Unified AI for Enterprise Automation FastAPI application.

Responsibilities:
  - Create the FastAPI application instance
  - Register all module routers under the /api/v1 prefix
  - Configure CORS middleware
  - Register global exception handlers
  - Trigger database table creation on startup (development convenience)

To run the server:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

import sys
from pathlib import Path

# Ensure backend directory is in sys.path so modules can import from config, models, auth, etc.
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.database import Base, engine
from config.settings import settings

# ------------------------------------------------------------------ #
# Import all ORM models before create_all() so SQLAlchemy registers
# every table in the metadata. Add new model imports here as modules
# are implemented.
# ------------------------------------------------------------------ #
import models  # noqa: F401 — triggers models/__init__.py which imports Role, User

# ------------------------------------------------------------------ #
# Module routers — import and register each router here as modules
# are implemented. Only the auth router is active at this stage.
# ------------------------------------------------------------------ #
from auth.router import router as auth_router
from modules.recruitment.router import router as recruitment_router
from modules.customer_support.router import router as customer_support_router

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
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------ #
# Register routers
# All API routes are versioned under /api/v1
# ------------------------------------------------------------------ #
API_PREFIX = "/api/v1"

app.include_router(auth_router,             prefix=API_PREFIX)
app.include_router(recruitment_router,      prefix=API_PREFIX)
app.include_router(customer_support_router, prefix=API_PREFIX)
# Future modules will be registered here:
# app.include_router(employee_router,  prefix=API_PREFIX)
# app.include_router(incident_router,  prefix=API_PREFIX)
# app.include_router(meeting_router,   prefix=API_PREFIX)
# app.include_router(analytics_router, prefix=API_PREFIX)

# ------------------------------------------------------------------ #
# Startup event — create all tables if they do not exist.
# In production, replace this with a proper Alembic migration.
# ------------------------------------------------------------------ #
@app.on_event("startup")
def on_startup() -> None:
    """
    Creates all database tables defined in the SQLAlchemy metadata.
    Safe to call multiple times — does not drop or modify existing tables.
    """
    try:
        Base.metadata.create_all(bind=engine)
        print("INFO:     Database tables verified/created successfully.")
    except Exception as exc:
        print(f"WARNING:  Could not connect to database on startup: {exc}")
        print("INFO:     FastAPI server will continue running. Please check DATABASE_URL in backend/.env")


# ------------------------------------------------------------------ #
# Health check — useful for load balancers and container orchestrators
# ------------------------------------------------------------------ #
@app.get("/health", tags=["Health"], summary="API health check")
def health_check() -> dict:
    """Returns a simple alive signal. No auth required."""
    return {"status": "ok", "app": settings.APP_NAME}
