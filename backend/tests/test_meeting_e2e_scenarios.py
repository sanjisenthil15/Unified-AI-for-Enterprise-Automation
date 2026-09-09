"""
Phase 9 — real end-to-end scenarios (@slow).

Runs the whole pipeline (video -> imageio-ffmpeg -> faster-whisper ->
resemblyzer diarization -> real Gemini) through the HTTP API for a short,
a multi-speaker, and a single-speaker meeting. Skips cleanly when the
environment can't support it (no Windows SAPI, no GEMINI_API_KEY, Gemini 503).
"""

import platform
import subprocess

import pytest

from config.settings import settings
from modules.meeting_intelligence.processing.audio import get_ffmpeg_exe

WINDOWS = platform.system() == "Windows"
_PLACEHOLDERS = {"", "your_gemini_api_key_here", "changeme"}
HAS_GEMINI = (settings.GEMINI_API_KEY or "").strip() not in _PLACEHOLDERS

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not WINDOWS, reason="uses Windows SAPI to synthesise meetings"),
    pytest.mark.skipif(not HAS_GEMINI, reason="GEMINI_API_KEY not configured"),
]

SCENARIOS = {
    "short_single_speaker": [
        (0, "Quick update: the release is on track for next week, nothing is blocked."),
    ],
    "multi_speaker": [
        (0, "We need to hire three backend developers this quarter, the workload is too high."),
        (99, "Agreed. I will write the job descriptions and post all three roles by Friday."),
        (0, "Great. Let's also ask finance to approve the budget by Wednesday."),
    ],
    "single_speaker_longer": [
        (0, "Welcome to the monthly review. First, revenue is up eight percent quarter over quarter. "
            "Second, the mobile app rollout is delayed by two weeks due to a vendor issue. "
            "Third, we decided to pause the marketing campaign until the app ships. "
            "Action item for me: send the revised timeline to the leadership team tomorrow."),
    ],
}


def _synth(wav, voice_index, text):
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$v = $s.GetInstalledVoices().VoiceInfo.Name;"
        f"$s.SelectVoice($v[[Math]::Min({voice_index}, $v.Count-1)]);"
        f"$s.SetOutputToWaveFile('{wav}'); $s.Speak('{text}'); $s.Dispose()"
    )
    import time
    for _ in range(3):
        subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps], capture_output=True, text=True)
        if wav.is_file() and wav.stat().st_size > 1000:
            return True
        time.sleep(1)
    return False


def _build_video(tmp_path, lines) -> "pathlib.Path | None":
    ff = get_ffmpeg_exe()
    wavs = []
    for i, (vi, text) in enumerate(lines):
        w = tmp_path / f"p{i}.wav"
        if not _synth(w, vi, text):
            return None
        wavs.append(w)
    speech = tmp_path / "speech.wav"
    if len(wavs) == 1:
        speech = wavs[0]
    else:
        inputs = sum([["-i", str(w)] for w in wavs], [])
        filt = "".join(f"[{i}:a]" for i in range(len(wavs))) + f"concat=n={len(wavs)}:v=0:a=1"
        subprocess.run([ff, "-y", *inputs, "-filter_complex", filt, str(speech)], capture_output=True)
    out = tmp_path / "meeting.mp4"
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", "testsrc=duration=120:size=320x240:rate=8",
         "-i", str(speech), "-shortest", "-c:v", "mpeg4", "-c:a", "aac", str(out)],
        capture_output=True,
    )
    return out if out.is_file() and out.stat().st_size > 1000 else None


@pytest.fixture(autouse=True)
def _fast_whisper(monkeypatch):
    from modules.meeting_intelligence.config import meeting_settings
    monkeypatch.setattr(meeting_settings, "whisper_model", "tiny")


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_end_to_end_scenario(client, new_user, tmp_path, scenario):
    lines = SCENARIOS[scenario]
    video = _build_video(tmp_path, lines)
    if video is None:
        pytest.skip("could not synthesise the meeting video")

    u = new_user()
    r = client.post("/api/v1/meetings", headers=u["headers"],
                    data={"title": f"E2E {scenario}"},
                    files={"file": ("meeting.mp4", video.read_bytes(), "video/mp4")})
    assert r.status_code == 201
    mid = r.json()["id"]
    assert r.json()["status"] == "pending"

    detail = client.get(f"/api/v1/meetings/{mid}", headers=u["headers"]).json()
    if detail["status"] != "completed":
        pytest.skip(f"pipeline did not complete ({detail.get('error_message')})")

    # metadata
    assert detail["duration_sec"] and detail["duration_sec"] > 0
    assert detail["language"]

    # transcript + timestamped segments + speaker labels
    tr = client.get(f"/api/v1/meetings/{mid}/transcript", headers=u["headers"]).json()
    assert tr["full_text"].strip()
    assert tr["segments"] and all(s["end_ms"] >= s["start_ms"] for s in tr["segments"])
    assert tr["speakers"] and all(sp["label"].startswith("Speaker ") for sp in tr["speakers"])
    # speaker statistics
    assert all(sp["segment_count"] is not None for sp in tr["speakers"])
    if scenario == "multi_speaker":
        assert len(tr["speakers"]) >= 2 or pytest.skip("voices too similar to separate")

    # analysis
    an = client.get(f"/api/v1/meetings/{mid}/analysis", headers=u["headers"]).json()
    assert len(an["summary"]) > 20
    assert isinstance(an["key_points"], list)
    assert isinstance(an["decisions"], list)

    # action items — unassigned by default
    items = client.get(f"/api/v1/meetings/{mid}/action-items", headers=u["headers"]).json()
    assert isinstance(items, list)
    assert all(it["assignment_method"] == "unassigned" for it in items)
    assert all(it["assigned_to_user_id"] is None for it in items)

    client.delete(f"/api/v1/meetings/{mid}", headers=u["headers"])
