"""Module-structure smoke tests for the Meeting Intelligence package."""

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


def test_config_defaults():
    from modules.meeting_intelligence.config import meeting_settings
    assert meeting_settings.whisper_model == "base"
    assert meeting_settings.whisper_device == "cpu"
    assert meeting_settings.diarization_backend == "resemblyzer"
    assert meeting_settings.ai_provider == "gemini"


def test_router_registered_in_app():
    from main import app
    paths = {r.path for r in app.routes}
    assert "/api/v1/meetings" in paths
    assert "/api/v1/meetings/{meeting_id}" in paths
    assert "/api/v1/meetings/{meeting_id}/transcript" in paths
    assert "/api/v1/meetings/{meeting_id}/analysis" in paths
    assert "/api/v1/meetings/{meeting_id}/action-items" in paths


def test_meeting_tables_registered():
    from config.database import Base
    for t in ("meetings", "meeting_transcripts", "meeting_transcript_segments",
              "meeting_speakers", "meeting_analyses", "meeting_action_items",
              "meeting_participants"):
        assert t in Base.metadata.tables
