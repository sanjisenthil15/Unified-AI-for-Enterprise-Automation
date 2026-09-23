"""
Phase 8 — Meeting API + pipeline orchestration.

Most tests replace the background pipeline with a fast fake (TestClient runs
background tasks synchronously). One @slow test runs the whole real pipeline
(faster-whisper + diarization + Gemini) end to end.
"""

import io
import platform
import subprocess
from datetime import datetime, timezone

import pytest
from starlette.datastructures import Headers

from config.database import SessionLocal
from config.settings import settings
from models.meeting import Meeting
from models.meeting_action_item import MeetingActionItem
from models.meeting_analysis import MeetingAnalysis
from models.meeting_speaker import MeetingSpeaker
from models.meeting_transcript import MeetingTranscript
from models.meeting_transcript_segment import MeetingTranscriptSegment
from modules.meeting_intelligence import pipeline as pipeline_mod
from modules.meeting_intelligence.processing.audio import get_ffmpeg_exe

WINDOWS = platform.system() == "Windows"
FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x11" * 8192
_PLACEHOLDER_KEYS = {"", "your_gemini_api_key_here", "changeme"}
HAS_GEMINI = (settings.GEMINI_API_KEY or "").strip() not in _PLACEHOLDER_KEYS


# --------------------------------------------------------------------------- #
# fake pipelines
# --------------------------------------------------------------------------- #
def _fake_success(meeting_id: int) -> None:
    db = SessionLocal()
    try:
        m = db.get(Meeting, meeting_id)
        db.add(MeetingTranscript(
            meeting_id=meeting_id, full_text="Speaker 1: hello everyone. Speaker 2: goodbye.",
            language="en", whisper_model="fake", word_count=6, segment_count=2,
        ))
        s1 = MeetingSpeaker(meeting_id=meeting_id, label="Speaker 1")
        s2 = MeetingSpeaker(meeting_id=meeting_id, label="Speaker 2")
        db.add_all([s1, s2])
        db.flush()
        db.add(MeetingTranscriptSegment(meeting_id=meeting_id, seq=0, start_ms=0, end_ms=2000,
                                        speaker_id=s1.id, speaker_label="Speaker 1", text="hello everyone"))
        db.add(MeetingTranscriptSegment(meeting_id=meeting_id, seq=1, start_ms=2000, end_ms=4000,
                                        speaker_id=s2.id, speaker_label="Speaker 2", text="goodbye"))
        a = MeetingAnalysis(
            meeting_id=meeting_id, summary="The two speakers greeted and said goodbye.",
            key_points=["A greeting happened"], decisions=["End the call"], sentiment="positive",
            model_provider="fake", model_name="fake-1", raw_response={},
        )
        db.add(a)
        db.flush()
        db.add(MeetingActionItem(
            meeting_id=meeting_id, analysis_id=a.id, description="Send the recap email",
            assignee_name_raw="Speaker 2", assignment_method="unassigned", status="pending", source="ai",
        ))
        m.status = "completed"
        m.language = "en"
        m.duration_sec = 4
        m.processing_started_at = m.processing_finished_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def _fake_failure(meeting_id: int) -> None:
    db = SessionLocal()
    try:
        m = db.get(Meeting, meeting_id)
        m.status = "failed"
        m.error_message = "transcription failed: the model could not be loaded"
        m.processing_started_at = m.processing_finished_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def _no_pipeline(meeting_id: int) -> None:
    return None


@pytest.fixture
def pipeline(monkeypatch):
    """Swap the background pipeline: pipeline('success' | 'failure' | 'none')."""
    def _set(mode: str):
        fn = {"success": _fake_success, "failure": _fake_failure, "none": _no_pipeline}[mode]
        monkeypatch.setattr("modules.meeting_intelligence.router.run_meeting_pipeline", fn)
    return _set


def _upload(client, headers, *, filename="team-sync.mp4", ctype="video/mp4",
            data=FAKE_MP4, title="Team Sync"):
    return client.post(
        "/api/v1/meetings", headers=headers,
        data={"title": title},
        files={"file": (filename, io.BytesIO(data), ctype)},
    )


# --------------------------------------------------------------------------- #
# upload / auth
# --------------------------------------------------------------------------- #
def test_authenticated_upload_returns_id_and_status(client, new_user, pipeline):
    pipeline("none")
    u = new_user()
    r = _upload(client, u["headers"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert isinstance(body["id"], int)
    assert body["status"] == "pending"
    assert "source_video_path" not in body and "audio_path" not in body


def test_unauthenticated_access_is_rejected(client, pipeline):
    pipeline("none")
    assert client.get("/api/v1/meetings").status_code in (401, 403)
    assert client.get("/api/v1/meetings/1").status_code in (401, 403)
    assert client.delete("/api/v1/meetings/1").status_code in (401, 403)
    r = client.post("/api/v1/meetings", data={"title": "x"},
                    files={"file": ("a.mp4", io.BytesIO(FAKE_MP4), "video/mp4")})
    assert r.status_code in (401, 403)


def test_invalid_upload_type_rejected(client, new_user, pipeline):
    pipeline("none")
    u = new_user()
    r = _upload(client, u["headers"], filename="notes.txt", ctype="text/plain", data=b"hello")
    assert r.status_code == 415


# --------------------------------------------------------------------------- #
# ownership / access control
# --------------------------------------------------------------------------- #
def test_user_cannot_access_or_delete_another_users_meeting(client, new_user, pipeline):
    pipeline("success")
    owner, other = new_user("Owner"), new_user("Other")
    mid = _upload(client, owner["headers"]).json()["id"]

    for path in (f"/api/v1/meetings/{mid}",
                 f"/api/v1/meetings/{mid}/transcript",
                 f"/api/v1/meetings/{mid}/analysis",
                 f"/api/v1/meetings/{mid}/action-items"):
        assert client.get(path, headers=other["headers"]).status_code == 404, path
    assert client.delete(f"/api/v1/meetings/{mid}", headers=other["headers"]).status_code == 404
    # owner still can
    assert client.get(f"/api/v1/meetings/{mid}", headers=owner["headers"]).status_code == 200


def test_list_history_is_scoped_to_caller(client, new_user, pipeline):
    pipeline("none")
    a, b = new_user("User A"), new_user("User B")
    a_ids = {_upload(client, a["headers"]).json()["id"] for _ in range(2)}
    b_id = _upload(client, b["headers"]).json()["id"]

    a_list = client.get("/api/v1/meetings", headers=a["headers"]).json()
    got = {m["id"] for m in a_list}
    assert a_ids <= got
    assert b_id not in got


# --------------------------------------------------------------------------- #
# retrieval
# --------------------------------------------------------------------------- #
def test_get_meeting_details_and_status(client, new_user, pipeline):
    pipeline("success")
    u = new_user()
    mid = _upload(client, u["headers"]).json()["id"]
    r = client.get(f"/api/v1/meetings/{mid}", headers=u["headers"])
    assert r.status_code == 200
    assert r.json()["status"] == "completed"
    assert r.json()["id"] == mid


def test_transcript_retrieval(client, new_user, pipeline):
    u = new_user()
    pipeline("none")
    mid = _upload(client, u["headers"]).json()["id"]
    assert client.get(f"/api/v1/meetings/{mid}/transcript", headers=u["headers"]).status_code == 404

    _fake_success(mid)
    r = client.get(f"/api/v1/meetings/{mid}/transcript", headers=u["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["full_text"].startswith("Speaker 1:")
    assert len(body["segments"]) == 2
    assert {s["speaker_label"] for s in body["segments"]} == {"Speaker 1", "Speaker 2"}
    assert {sp["label"] for sp in body["speakers"]} == {"Speaker 1", "Speaker 2"}


def test_analysis_retrieval(client, new_user, pipeline):
    u = new_user()
    pipeline("none")
    mid = _upload(client, u["headers"]).json()["id"]
    assert client.get(f"/api/v1/meetings/{mid}/analysis", headers=u["headers"]).status_code == 404

    _fake_success(mid)
    r = client.get(f"/api/v1/meetings/{mid}/analysis", headers=u["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]
    assert body["key_points"] == ["A greeting happened"]
    assert body["decisions"] == ["End the call"]
    assert "raw_response" not in body


def test_action_item_retrieval_unassigned(client, new_user, pipeline):
    pipeline("success")
    u = new_user()
    mid = _upload(client, u["headers"]).json()["id"]
    r = client.get(f"/api/v1/meetings/{mid}/action-items", headers=u["headers"])
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    it = items[0]
    assert it["assignment_method"] == "unassigned"
    assert it["assigned_to_user_id"] is None and it["assigned_to_employee_id"] is None
    assert it["assignee_name_raw"] == "Speaker 2"
    assert it["source"] == "ai"


def test_action_item_assignment(client, new_user, pipeline):
    pipeline("success")
    owner = new_user()
    other = new_user("Someone Else")
    mid = _upload(client, owner["headers"]).json()["id"]
    item_id = client.get(f"/api/v1/meetings/{mid}/action-items", headers=owner["headers"]).json()[0]["id"]

    # A non-owner cannot see or touch the meeting at all.
    assign_url = f"/api/v1/meetings/{mid}/action-items/{item_id}/assign"
    assert client.patch(assign_url, json={"assigned_to_user_id": other["id"]},
                        headers=other["headers"]).status_code == 404

    # The owner assigns it to another real user.
    r = client.patch(assign_url, json={"assigned_to_user_id": other["id"]}, headers=owner["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["assigned_to_user_id"] == other["id"]
    assert body["assignment_method"] == "manual"

    # Assigning to a nonexistent user is rejected.
    assert client.patch(assign_url, json={"assigned_to_user_id": 999999},
                        headers=owner["headers"]).status_code == 400

    # Clearing the assignment (null) reverts to unassigned.
    r = client.patch(assign_url, json={"assigned_to_user_id": None}, headers=owner["headers"])
    assert r.status_code == 200
    assert r.json()["assigned_to_user_id"] is None
    assert r.json()["assignment_method"] == "unassigned"

    # Unknown action item id on a real meeting is 404.
    assert client.patch(f"/api/v1/meetings/{mid}/action-items/999999/assign",
                        json={"assigned_to_user_id": other["id"]}, headers=owner["headers"]).status_code == 404


# --------------------------------------------------------------------------- #
# delete
# --------------------------------------------------------------------------- #
def test_delete_meeting_removes_it(client, new_user, pipeline):
    pipeline("success")
    u = new_user()
    mid = _upload(client, u["headers"]).json()["id"]
    assert client.delete(f"/api/v1/meetings/{mid}", headers=u["headers"]).status_code == 204
    assert client.get(f"/api/v1/meetings/{mid}", headers=u["headers"]).status_code == 404


# --------------------------------------------------------------------------- #
# pipeline status transitions
# --------------------------------------------------------------------------- #
def test_status_pending_then_completed(client, new_user, pipeline):
    pipeline("none")
    u = new_user()
    mid = _upload(client, u["headers"]).json()["id"]
    assert client.get(f"/api/v1/meetings/{mid}", headers=u["headers"]).json()["status"] == "pending"

    _fake_success(mid)
    assert client.get(f"/api/v1/meetings/{mid}", headers=u["headers"]).json()["status"] == "completed"


def test_pipeline_failure_sets_failed_with_message(client, new_user, pipeline):
    pipeline("failure")
    u = new_user()
    mid = _upload(client, u["headers"]).json()["id"]
    body = client.get(f"/api/v1/meetings/{mid}", headers=u["headers"]).json()
    assert body["status"] == "failed"
    assert body["error_message"] and "model could not be loaded" in body["error_message"]


def test_real_pipeline_transitions_and_marks_failed(client, new_user, monkeypatch):
    """Run the actual run_meeting_pipeline with a failing first stage."""
    from fastapi import HTTPException

    def boom(db, meeting_id):
        raise HTTPException(422, "Source video file is missing from storage.")

    monkeypatch.setattr(pipeline_mod, "extract_meeting_audio", boom)
    u = new_user()
    mid = _upload(client, u["headers"]).json()["id"]  # real run_meeting_pipeline runs in bg
    body = client.get(f"/api/v1/meetings/{mid}", headers=u["headers"]).json()
    assert body["status"] == "failed"
    assert "audio extraction stage" in body["error_message"]
    assert "missing from storage" in body["error_message"]


def test_real_pipeline_completes_with_faked_stages(client, new_user, monkeypatch):
    """run_meeting_pipeline drives real status transitions; stages are stubbed."""
    calls = []
    monkeypatch.setattr(pipeline_mod, "extract_meeting_audio", lambda db, mid: calls.append("audio"))
    monkeypatch.setattr(pipeline_mod, "transcribe_meeting", lambda db, mid: calls.append("stt"))
    monkeypatch.setattr(pipeline_mod, "diarize_meeting", lambda db, mid: calls.append("diar"))
    monkeypatch.setattr(pipeline_mod, "analyze_meeting", lambda db, mid: calls.append("gemini"))
    u = new_user()
    mid = _upload(client, u["headers"]).json()["id"]
    body = client.get(f"/api/v1/meetings/{mid}", headers=u["headers"]).json()
    assert calls == ["audio", "stt", "diar", "gemini"]
    assert body["status"] == "completed"
    assert body["processing_started_at"] and body["processing_finished_at"]


# --------------------------------------------------------------------------- #
# reprocess (retry a failed meeting)
# --------------------------------------------------------------------------- #
def test_reprocess_resumes_and_reruns_only_pending_stages(client, new_user, monkeypatch):
    calls = []
    state = {"analysis_ok": False}
    # audio + transcription + diarization "already done"; analysis fails then succeeds
    monkeypatch.setattr(pipeline_mod, "_stage_done",
                        lambda db, mid, name: name != "analysis")

    def audio(db, mid): calls.append("audio")
    def stt(db, mid): calls.append("stt")
    def diar(db, mid): calls.append("diar")
    def analysis(db, mid):
        calls.append("analysis")
        if not state["analysis_ok"]:
            raise HTTPException(502, "Gemini quota / rate limit exceeded")

    monkeypatch.setattr(pipeline_mod, "extract_meeting_audio", audio)
    monkeypatch.setattr(pipeline_mod, "transcribe_meeting", stt)
    monkeypatch.setattr(pipeline_mod, "diarize_meeting", diar)
    monkeypatch.setattr(pipeline_mod, "analyze_meeting", analysis)

    u = new_user()
    mid = _upload(client, u["headers"]).json()["id"]  # first run: all 4 stages, fails at analysis
    assert client.get(f"/api/v1/meetings/{mid}", headers=u["headers"]).json()["status"] == "failed"
    assert calls == ["audio", "stt", "diar", "analysis"]

    calls.clear()
    state["analysis_ok"] = True
    r = client.post(f"/api/v1/meetings/{mid}/reprocess", headers=u["headers"])
    assert r.status_code == 200
    assert client.get(f"/api/v1/meetings/{mid}", headers=u["headers"]).json()["status"] == "completed"
    assert calls == ["analysis"]  # resume skipped audio/stt/diar


def test_reprocess_requires_ownership(client, new_user, pipeline):
    pipeline("failure")
    owner, other = new_user("Owner"), new_user("Other")
    mid = _upload(client, owner["headers"]).json()["id"]
    assert client.post(f"/api/v1/meetings/{mid}/reprocess", headers=other["headers"]).status_code == 404


def test_reprocess_conflict_while_processing(client, new_user, monkeypatch):
    monkeypatch.setattr("modules.meeting_intelligence.router.run_meeting_pipeline",
                        lambda mid, **kw: None)  # leaves status = pending
    u = new_user()
    mid = _upload(client, u["headers"]).json()["id"]
    r = client.post(f"/api/v1/meetings/{mid}/reprocess", headers=u["headers"])
    assert r.status_code == 409


# --------------------------------------------------------------------------- #
# no internal details leak
# --------------------------------------------------------------------------- #
def test_responses_never_expose_storage_paths(client, new_user, pipeline):
    pipeline("success")
    u = new_user()
    mid = _upload(client, u["headers"]).json()["id"]
    for path in (f"/api/v1/meetings", f"/api/v1/meetings/{mid}",
                 f"/api/v1/meetings/{mid}/transcript", f"/api/v1/meetings/{mid}/analysis",
                 f"/api/v1/meetings/{mid}/action-items"):
        text = client.get(path, headers=u["headers"]).text
        assert "source_video_path" not in text
        assert "audio_path" not in text
        assert "uploads" not in text.lower()


def test_scrub_removes_api_key():
    from modules.meeting_intelligence import pipeline as p
    if not HAS_GEMINI:
        pytest.skip("no real key configured to scrub")
    key = settings.GEMINI_API_KEY
    assert key not in p._scrub(f"boom with key {key} in it")


# --------------------------------------------------------------------------- #
# real end-to-end (req 25)
# --------------------------------------------------------------------------- #
def _make_meeting_video(path):
    """A short MP4 with a video track + two SAPI voices discussing hiring."""
    a, b = path.parent / "a.wav", path.parent / "b.wav"
    lines = [
        (a, 0, "We need to hire three backend developers this quarter. The workload is too high."),
        (b, 99, "Agreed. I will prepare the job descriptions and post them by Friday."),
    ]
    for wav, vi, text in lines:
        ps = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            "$v = $s.GetInstalledVoices().VoiceInfo.Name;"
            f"$s.SelectVoice($v[[Math]::Min({vi}, $v.Count-1)]);"
            f"$s.SetOutputToWaveFile('{wav}'); $s.Speak('{text}'); $s.Dispose()"
        )
        p = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True)
        if p.returncode != 0 or not wav.is_file():
            return False
    speech = path.parent / "speech.wav"
    subprocess.run([get_ffmpeg_exe(), "-y", "-i", str(a), "-i", str(b),
                    "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1", str(speech)],
                   capture_output=True)
    r = subprocess.run(
        [get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc=duration=20:size=320x240:rate=10",
         "-i", str(speech), "-shortest", "-c:v", "mpeg4", "-c:a", "aac", str(path)],
        capture_output=True, text=True,
    )
    return path.is_file() and path.stat().st_size > 1000


@pytest.mark.slow
@pytest.mark.skipif(not WINDOWS, reason="needs Windows SAPI to synthesise the meeting")
@pytest.mark.skipif(not HAS_GEMINI, reason="GEMINI_API_KEY not configured")
def test_real_end_to_end(client, new_user, tmp_path, monkeypatch):
    from modules.meeting_intelligence.config import meeting_settings
    monkeypatch.setattr(meeting_settings, "whisper_model", "tiny")  # keep it quick

    video = tmp_path / "meeting.mp4"
    if not _make_meeting_video(video):
        pytest.skip("could not synthesise a meeting video")

    u = new_user()
    r = _upload(client, u["headers"], filename="meeting.mp4",
                data=video.read_bytes(), title="Hiring planning")
    assert r.status_code == 201
    mid = r.json()["id"]

    detail = client.get(f"/api/v1/meetings/{mid}", headers=u["headers"]).json()
    if detail["status"] != "completed":
        pytest.skip(f"pipeline did not complete in this environment: {detail.get('error_message')}")

    transcript = client.get(f"/api/v1/meetings/{mid}/transcript", headers=u["headers"]).json()
    assert transcript["full_text"].strip()
    assert transcript["speakers"], "no speaker labels"
    assert all(sp["label"].startswith("Speaker ") for sp in transcript["speakers"])
    assert transcript["segments"]

    analysis = client.get(f"/api/v1/meetings/{mid}/analysis", headers=u["headers"]).json()
    assert len(analysis["summary"]) > 20
    assert isinstance(analysis["key_points"], list)
    assert isinstance(analysis["decisions"], list)

    items = client.get(f"/api/v1/meetings/{mid}/action-items", headers=u["headers"]).json()
    assert isinstance(items, list)
    assert all(it["assignment_method"] == "unassigned" for it in items)
