"""
Phase 7 — AI analysis (Gemini, provider-abstracted).

Deterministic tests use an injected fake provider. Parser tests exercise the
JSON handling. One @slow test hits real Gemini when GEMINI_API_KEY is set.
"""

import pytest
from fastapi import HTTPException

from config.settings import settings
from models.meeting import Meeting
from models.meeting_action_item import MeetingActionItem
from models.meeting_analysis import MeetingAnalysis
from models.meeting_transcript import MeetingTranscript
from models.meeting_transcript_segment import MeetingTranscriptSegment
from modules.meeting_intelligence import service
from modules.meeting_intelligence.processing.analysis import (
    AnalysisError,
    AnalysisProvider,
    AnalysisResult,
    ExtractedActionItem,
    GeminiAnalysisProvider,
    get_analysis_provider,
    parse_json_response,
    result_from_dict,
)

RESULT = AnalysisResult(
    summary="The team agreed to hire three developers and to prepare job descriptions this week.",
    key_points=["Three developers are needed", "The recruitment timeline is tight"],
    decisions=["Hire three developers", "Job descriptions are due Friday"],
    action_items=[
        ExtractedActionItem("Prepare the job descriptions by Friday", "Speaker 2", "high", 0.92),
        ExtractedActionItem("Review the recruitment budget", None, None, 0.4),
    ],
    sentiment="neutral",
    model_provider="fake",
    model_name="fake-analyzer",
    raw_response={"summary": "stub", "ok": True},
)


class FakeProvider(AnalysisProvider):
    name = "fake"

    def __init__(self, result=RESULT, error=None):
        self.result = result
        self.error = error
        self.seen_text = None

    def analyze(self, transcript_text):
        self.seen_text = transcript_text
        if self.error:
            raise self.error
        return self.result


@pytest.fixture
def meeting_with_transcript(db, meeting_owner):
    m = Meeting(created_by=meeting_owner, title="Hiring sync", status="pending")
    db.add(m)
    db.flush()
    db.add(MeetingTranscript(
        meeting_id=m.id,
        full_text="We need three developers. I'll prepare the job descriptions. Finish by Friday.",
        segment_count=3,
    ))
    rows = [
        (0, 0, 3000, "Speaker 1", "We need three developers."),
        (1, 3000, 7000, "Speaker 2", "I'll prepare the job descriptions."),
        (2, 7000, 9000, "Speaker 1", "Please finish it by Friday."),
    ]
    for seq, s, e, spk, txt in rows:
        db.add(MeetingTranscriptSegment(
            meeting_id=m.id, seq=seq, start_ms=s, end_ms=e, speaker_label=spk, text=txt,
        ))
    db.commit()
    db.refresh(m)
    return m


def _analysis(db, mid):
    return db.query(MeetingAnalysis).filter_by(meeting_id=mid).first()


def _items(db, mid):
    return db.query(MeetingActionItem).filter_by(meeting_id=mid).order_by(MeetingActionItem.id).all()


# --------------------------------------------------------------------------- #
# persistence
# --------------------------------------------------------------------------- #
def test_analysis_persisted(db, meeting_with_transcript):
    a = service.analyze_meeting(db, meeting_with_transcript.id, provider=FakeProvider())
    assert a.summary.startswith("The team agreed")
    assert a.key_points == RESULT.key_points
    assert a.decisions == RESULT.decisions
    assert a.sentiment == "neutral"
    assert a.model_provider == "fake" and a.model_name == "fake-analyzer"
    assert a.raw_response == {"summary": "stub", "ok": True}

    db.expire_all()
    reloaded = _analysis(db, meeting_with_transcript.id)
    assert isinstance(reloaded.key_points, list) and isinstance(reloaded.decisions, list)


def test_action_items_created_unassigned(db, meeting_with_transcript):
    a = service.analyze_meeting(db, meeting_with_transcript.id, provider=FakeProvider())
    items = _items(db, meeting_with_transcript.id)
    assert len(items) == 2
    for it in items:
        assert it.source == "ai"
        assert it.assignment_method == "unassigned"
        assert it.assigned_to_user_id is None and it.assigned_to_employee_id is None
        assert it.status == "pending"
        assert it.analysis_id == a.id
    first = items[0]
    assert first.description == "Prepare the job descriptions by Friday"
    assert first.assignee_name_raw == "Speaker 2"      # kept as text, NOT resolved
    assert first.priority == "high"
    assert first.ai_confidence == pytest.approx(0.92)
    assert items[1].assignee_name_raw is None and items[1].priority is None


def test_diarized_transcript_is_sent_to_provider(db, meeting_with_transcript):
    p = FakeProvider()
    service.analyze_meeting(db, meeting_with_transcript.id, provider=p)
    assert "Speaker 1: We need three developers." in p.seen_text
    assert "Speaker 2: I'll prepare the job descriptions." in p.seen_text


def test_transcript_truncated_to_limit(db, meeting_with_transcript, monkeypatch):
    from modules.meeting_intelligence import config as cfg
    monkeypatch.setattr(cfg.meeting_settings, "analysis_max_transcript_chars", 20)
    p = FakeProvider()
    service.analyze_meeting(db, meeting_with_transcript.id, provider=p)
    assert len(p.seen_text) <= 20


# --------------------------------------------------------------------------- #
# errors
# --------------------------------------------------------------------------- #
def test_no_transcript_422(db, meeting_owner):
    m = Meeting(created_by=meeting_owner, title="No transcript", status="pending")
    db.add(m)
    db.commit()
    with pytest.raises(HTTPException) as ei:
        service.analyze_meeting(db, m.id, provider=FakeProvider())
    assert ei.value.status_code == 422


def test_provider_config_error_is_503_and_persists_nothing(db, meeting_with_transcript):
    p = FakeProvider(error=AnalysisError("no key", kind="config"))
    with pytest.raises(HTTPException) as ei:
        service.analyze_meeting(db, meeting_with_transcript.id, provider=p)
    assert ei.value.status_code == 503
    db.rollback()
    assert _analysis(db, meeting_with_transcript.id) is None
    assert _items(db, meeting_with_transcript.id) == []


def test_provider_api_error_is_502(db, meeting_with_transcript):
    p = FakeProvider(error=AnalysisError("boom", kind="api"))
    with pytest.raises(HTTPException) as ei:
        service.analyze_meeting(db, meeting_with_transcript.id, provider=p)
    assert ei.value.status_code == 502


# --------------------------------------------------------------------------- #
# reprocess
# --------------------------------------------------------------------------- #
def test_reprocess_replaces_analysis_keeps_assigned_items(db, meeting_owner, meeting_with_transcript):
    service.analyze_meeting(db, meeting_with_transcript.id, provider=FakeProvider())
    items = _items(db, meeting_with_transcript.id)
    # a human assigns the first item
    items[0].assigned_to_user_id = meeting_owner
    items[0].assignment_method = "manual"
    db.commit()
    kept_id = items[0].id

    other = AnalysisResult(
        summary="Different summary entirely.", key_points=["x"], decisions=[],
        action_items=[ExtractedActionItem("A brand new task", None, None, 0.7)],
        sentiment="positive", model_provider="fake", model_name="fake-2", raw_response={},
    )
    a2 = service.analyze_meeting(db, meeting_with_transcript.id, provider=FakeProvider(result=other))
    assert a2.summary == "Different summary entirely."
    assert db.query(MeetingAnalysis).filter_by(meeting_id=meeting_with_transcript.id).count() == 1

    remaining = _items(db, meeting_with_transcript.id)
    descriptions = {i.description for i in remaining}
    assert "A brand new task" in descriptions
    assert any(i.id == kept_id for i in remaining)                 # manual item survived
    assert "Review the recruitment budget" not in descriptions     # untouched AI item replaced


# --------------------------------------------------------------------------- #
# parser / provider unit tests
# --------------------------------------------------------------------------- #
def test_parse_json_response_handles_fences():
    assert parse_json_response('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_response('{"a": 2}') == {"a": 2}


def test_parse_json_response_rejects_garbage():
    with pytest.raises(AnalysisError) as ei:
        parse_json_response("Sorry, I cannot do that.")
    assert ei.value.kind == "parse"


def test_result_from_dict_validates_and_filters():
    data = {
        "summary": "ok",
        "key_points": ["a", "", "  ", "b"],
        "decisions": "not a list",
        "sentiment": "grumpy",
        "action_items": [
            {"description": "real task", "assignee": "Bob", "priority": "urgent", "confidence": 2},
            {"assignee": "no description"},
            "not a dict",
        ],
    }
    r = result_from_dict(data, provider="gemini", model="m")
    assert r.key_points == ["a", "b"]
    assert r.decisions == []
    assert r.sentiment is None            # "grumpy" rejected
    assert len(r.action_items) == 1
    assert r.action_items[0].priority is None and r.action_items[0].confidence is None


def test_result_from_dict_requires_summary():
    with pytest.raises(AnalysisError):
        result_from_dict({"summary": "  "}, provider="gemini", model="m")


def test_get_analysis_provider():
    assert isinstance(get_analysis_provider("gemini"), GeminiAnalysisProvider)
    with pytest.raises(AnalysisError):
        get_analysis_provider("ollama")


def test_gemini_provider_without_key_raises_config_error():
    with pytest.raises(AnalysisError) as ei:
        GeminiAnalysisProvider(api_key="").analyze("Speaker 1: hi")
    assert ei.value.kind == "config"


# --------------------------------------------------------------------------- #
# real Gemini
# --------------------------------------------------------------------------- #
_PLACEHOLDER_KEYS = {"", "your_gemini_api_key_here", "changeme"}


@pytest.mark.slow
@pytest.mark.skipif(
    (settings.GEMINI_API_KEY or "").strip() in _PLACEHOLDER_KEYS,
    reason="GEMINI_API_KEY not configured",
)
def test_real_gemini_analysis(db, meeting_with_transcript):
    try:
        a = service.analyze_meeting(db, meeting_with_transcript.id, provider=GeminiAnalysisProvider())
    except HTTPException as exc:  # invalid key / quota / transient API problem
        pytest.skip(f"Gemini not usable in this environment: {exc.detail}")
    assert a.summary and len(a.summary) > 20
    assert isinstance(a.key_points, list)
    assert a.model_provider == "gemini"
    for it in _items(db, meeting_with_transcript.id):
        assert it.assignment_method == "unassigned"
