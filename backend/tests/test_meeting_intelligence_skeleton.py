"""Phase 1 smoke test: the Meeting Intelligence skeleton imports cleanly and
is isolated (no routes wired, no tables registered)."""

import importlib

import pytest

MODULES = [
    "modules.meeting_intelligence",
    "modules.meeting_intelligence.config",
    "modules.meeting_intelligence.router",
    "modules.meeting_intelligence.schemas",
    "modules.meeting_intelligence.service",
    "modules.meeting_intelligence.storage",
    "modules.meeting_intelligence.pipeline",
    "modules.meeting_intelligence.processing",
    "modules.meeting_intelligence.processing.audio",
    "modules.meeting_intelligence.processing.transcription",
    "modules.meeting_intelligence.processing.diarization",
    "modules.meeting_intelligence.processing.merge",
    "modules.meeting_intelligence.processing.analysis",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports(name):
    importlib.import_module(name)


def test_router_has_no_routes_yet():
    from modules.meeting_intelligence.router import router
    assert router.prefix == "/meetings"
    assert router.routes == []


def test_config_defaults():
    from modules.meeting_intelligence.config import meeting_settings
    assert meeting_settings.whisper_model == "base"
    assert meeting_settings.diarization_backend == "resemblyzer"
    assert meeting_settings.ai_provider == "gemini"
    assert meeting_settings.storage_path.name == "meetings"


def test_meeting_router_not_registered_in_app():
    """Phase 1 must not expose any /meetings endpoint."""
    from main import app
    paths = {r.path for r in app.routes}
    assert not any(p.startswith("/api/v1/meetings") for p in paths)


def test_meeting_tables_not_registered():
    """Phase 1 must not add Meeting Intelligence tables to the ORM metadata."""
    from config.database import Base
    assert "meetings" not in Base.metadata.tables
