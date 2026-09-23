"""Run: python -m pytest online_tests -q. No DB connection or real AI required."""

import asyncio
import base64
import os
import time
from types import SimpleNamespace
from uuid import uuid4

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from core.dependencies import get_current_user
from main import app
from modules.meeting_online import processing, router
from modules.meeting_online.schemas import ActionItemResult, LiveAnalysisResult, StartMeeting
from modules.meeting_online.service import OnlineMeetingService

BASE = "/api/v1/meetings/online"


def fake_analysis(segments):
    return LiveAnalysisResult(
        summary="Dashboard work was discussed.",
        decisions=["Deliver Friday"],
        action_items=[ActionItemResult(description="Finish dashboard", assignee="Speaker 1",
                                       priority="high", confidence=0.9)],
        transcript_count=len(segments),
    )


def fake_transcriber(data, mime):
    return SimpleNamespace(segments=[
        SimpleNamespace(text="Finish dashboard Friday", start_ms=0, end_ms=1000)
    ])


@pytest.fixture
def client(monkeypatch):
    instance = OnlineMeetingService(fake_transcriber, fake_analysis)
    monkeypatch.setattr(router, "service", instance)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def start(client):
    response = client.post(BASE, json={"title": "Live sync", "request_id": str(uuid4())})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def connect(client, mid, cid=None):
    ticket = client.post(f"{BASE}/{mid}/ws-ticket").json()["ticket"]
    return ticket, str(cid or uuid4())


def receive(ws, kind):
    for _ in range(30):
        event = ws.receive_json()
        if event["type"] == kind:
            return event
    pytest.fail(f"No {kind} event received")


def join(ws, ticket, cid):
    ws.send_json({"type": "auth", "ticket": ticket})
    assert ws.receive_json()["type"] == "authenticated"
    ws.send_json({"type": "join", "client_id": cid})
    event = receive(ws, "join")
    receive(ws, "snapshot")
    return event


def text_event(**kwargs):
    return {"type": "transcript", "message_id": str(uuid4()),
            "text": "We decided to deliver Friday. I will finish the dashboard.",
            "start_ms": 0, "end_ms": 1000, **kwargs}


def test_create_idempotent_duplicate_invalid_and_owner(client):
    request = {"title": "Sync", "request_id": str(uuid4())}
    first = client.post(BASE, json=request)
    mid = first.json()["id"]
    assert client.post(BASE, json=request).json()["id"] == mid
    assert client.post(BASE, json={**request, "title": "Other"}).status_code == 409
    assert client.post(BASE, json={**request, "request_id": str(uuid4())}).status_code == 409
    assert client.post(BASE, json={"title": " "}).status_code == 422
    assert client.get(f"{BASE}/missing").status_code == 404
    assert client.post(f"{BASE}/missing/end").status_code == 404
    assert client.get(f"{BASE}/{mid}").json()["status"] == "active"
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=2)
    assert client.get(f"{BASE}/{mid}").status_code == 404
    assert client.post(f"{BASE}/{mid}/end").status_code == 404
    assert client.post(f"{BASE}/{mid}/ws-ticket").status_code == 404


def test_transcript_analysis_decisions_actions_end(client):
    mid = start(client)
    ticket, cid = connect(client, mid)
    with client.websocket_connect(f"{BASE}/{mid}/ws") as ws:
        assert join(ws, ticket, cid)["speaker"] == "Speaker 1"
        event = text_event()
        ws.send_json(event)
        assert receive(ws, "transcript")["speaker"] == "Speaker 1"
        result = receive(ws, "analysis")
        assert result["action_items"][0]["assignee"] == "Speaker 1"
        assert receive(ws, "decision")["description"] == "Deliver Friday"
        assert receive(ws, "action_item")["confidence"] == 0.9
        ws.send_json(event)
        assert receive(ws, "ack")["duplicate"]
        assert len(client.get(f"{BASE}/{mid}").json()["transcript"]) == 1
        assert client.post(f"{BASE}/{mid}/end").status_code == 200
        assert receive(ws, "meeting_ended")["session"]["status"] == "ended"
        assert client.post(f"{BASE}/{mid}/end").json()["status"] == "ended"
        ws.send_json(text_event())
        assert receive(ws, "error")["code"] == "invalid_message"


@pytest.mark.parametrize("message", [
    "{", "[]", '{"type":"unsupported"}',
    '{"type":"audio","data":""}', '{"type":"transcript","text":" "}',
])
def test_malformed_does_not_kill_session(client, message):
    mid = start(client)
    ticket, cid = connect(client, mid)
    with client.websocket_connect(f"{BASE}/{mid}/ws") as ws:
        join(ws, ticket, cid)
        ws.send_text(message)
        assert receive(ws, "error")["recoverable"]
        ws.send_json({"type": "ping"})
        assert receive(ws, "pong")["type"] == "pong"


def test_speakers_disconnect_reconnect_leave(client):
    mid = start(client)
    ticket, cid = connect(client, mid)
    with client.websocket_connect(f"{BASE}/{mid}/ws") as ws:
        assert join(ws, ticket, cid)["speaker"] == "Speaker 1"
    ticket2, cid2 = connect(client, mid)
    with client.websocket_connect(f"{BASE}/{mid}/ws") as ws:
        assert join(ws, ticket2, cid2)["speaker"] == "Speaker 2"
        ws.send_json({"type": "leave"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    ticket3, _ = connect(client, mid, cid)
    with client.websocket_connect(f"{BASE}/{mid}/ws") as ws:
        assert join(ws, ticket3, cid)["speaker"] == "Speaker 1"
        people = client.get(f"{BASE}/{mid}").json()["participants"]
        assert people[0]["connected"]
        assert not people[1]["connected"]


def test_audio_and_transcription_failure(client):
    mid = start(client)
    ticket, cid = connect(client, mid)
    with client.websocket_connect(f"{BASE}/{mid}/ws") as ws:
        join(ws, ticket, cid)
        ws.send_json({"type": "audio", "message_id": str(uuid4()), "data": "YQ==",
                      "mime_type": "audio/webm", "start_ms": 5000, "end_ms": 6000})
        segment = receive(ws, "transcript")
        assert segment["source"] == "audio"
        assert segment["start_ms"] == 5000
        def fail(*args):
            raise RuntimeError("private provider details")
        router.service.transcriber = fail
        ws.send_json({"type": "audio", "message_id": str(uuid4()), "data": "YQ==",
                      "mime_type": "audio/webm", "start_ms": 6000, "end_ms": 7000})
        assert receive(ws, "error")["code"] == "transcription_failed"
        assert client.get(f"{BASE}/{mid}").json()["status"] == "active"


def test_ai_failure_preserves_transcript_and_can_retry(client):
    def fail(*args):
        raise RuntimeError("secret key must not be returned")
    router.service.analyzer = fail
    mid = start(client)
    ticket, cid = connect(client, mid)
    with client.websocket_connect(f"{BASE}/{mid}/ws") as ws:
        join(ws, ticket, cid)
        ws.send_json(text_event())
        error = receive(ws, "error")
        assert error["code"] == "analysis_failed"
        assert "secret key" not in error["message"]
        assert len(client.get(f"{BASE}/{mid}").json()["transcript"]) == 1
        receive(ws, "snapshot")
        router.service.analyzer = fake_analysis
        ws.send_json({"type": "analyze"})
        assert receive(ws, "analysis")["summary"]


def test_ticket_required_single_use_and_origin(client):
    mid = start(client)
    ticket, cid = connect(client, mid)
    with client.websocket_connect(f"{BASE}/{mid}/ws") as ws:
        join(ws, ticket, cid)
    with client.websocket_connect(f"{BASE}/{mid}/ws") as ws:
        ws.send_json({"type": "auth", "ticket": ticket})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"{BASE}/{mid}/ws", headers={"origin": "https://untrusted.example"}):
            pass
    router.service.tickets["expired"] = (mid, time.monotonic() - 1)
    assert not router.service.consume_ticket(mid, "expired")


def test_real_auth_dependency_is_not_bypassed(client):
    from config.settings import settings
    original = settings.AUTH_DISABLED
    settings.AUTH_DISABLED = False
    app.dependency_overrides.clear()
    try:
        assert client.post(BASE, json={"title": "Sync", "request_id": str(uuid4())}).status_code == 401
    finally:
        settings.AUTH_DISABLED = original


def test_transcriber_rejects_invalid_data():
    with pytest.raises(ValueError):
        processing.transcribe_chunk("!", "audio/webm")
    with pytest.raises(ValueError):
        processing.transcribe_chunk("", "audio/webm")


def test_transcriber_reuses_audio_and_whisper(monkeypatch):
    import wave
    called = []
    def extract(source, target, **kwargs):
        assert source.read_bytes() == b"clip"
        with wave.open(str(target), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b"\x00\x00" * 16000)
        called.append(source)
    monkeypatch.setattr(processing, "extract_audio", extract)
    monkeypatch.setattr(processing, "transcribe_audio", lambda path: "transcribed")
    assert processing.transcribe_chunk(base64.b64encode(b"clip").decode(), "audio/webm") == "transcribed"
    assert not called[0].exists()


def test_analysis_adapter_reuses_provider(monkeypatch):
    from modules.meeting_intelligence.processing.analysis import AnalysisResult, ExtractedActionItem
    def analyze(text):
        assert "Speaker 2: I will deliver." in text
        return AnalysisResult(summary="Delivery", decisions=["Friday"],
                              action_items=[ExtractedActionItem("Deliver", "Speaker 2", "high", 0.8)])
    monkeypatch.setattr(processing, "get_analysis_provider", lambda: SimpleNamespace(analyze=analyze))
    result = processing.analyze_transcript([SimpleNamespace(speaker="Speaker 2", text="I will deliver.")])
    assert result.action_items[0].assignee == "Speaker 2"
    assert result.decisions == ["Friday"]


def test_empty_end_and_retention():
    async def scenario():
        service = OnlineMeetingService()
        view = service.create(1, StartMeeting(title="Empty", request_id=uuid4()))
        state = service.get(view.id)
        service.end(state)
        await state.end_task
        assert state.view.status == "ended"
        assert service.get(view.id).view.transcript == []
    asyncio.run(scenario())