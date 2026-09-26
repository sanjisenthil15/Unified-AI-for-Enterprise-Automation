"""
Phase 5 — offline speech-to-text (faster-whisper).

Persistence / timestamp / error tests use an injected fake transcriber
(deterministic, fast). Two tests exercise the real faster-whisper model
(CPU, int8, "tiny") to prove it runs fully offline.
"""

import platform
import subprocess
import wave

import pytest
from fastapi import HTTPException
from sqlalchemy import inspect, text

from models.meeting import Meeting
from models.meeting_transcript import MeetingTranscript
from models.meeting_transcript_segment import MeetingTranscriptSegment
from modules.meeting_intelligence import service
from modules.meeting_intelligence.processing.transcription import (
    AudioNotFoundError,
    TranscriptionError,
    TranscriptionResult,
    TranscriptSegment,
    transcribe_audio,
)
from modules.meeting_intelligence.storage import LocalMeetingVideoStorage


# --------------------------------------------------------------------------- #
# helpers / fixtures
# --------------------------------------------------------------------------- #
def _write_wav(path, seconds=1, sample_rate=16_000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * sample_rate * seconds)


def fake_transcriber(_audio_path: str) -> TranscriptionResult:
    return TranscriptionResult(
        text="Hello team. Let us start the planning meeting.",
        language="en",
        language_probability=0.98,
        duration_sec=9.0,
        model="fake-whisper",
        segments=[
            TranscriptSegment(0, 0, 2200, "Hello team."),
            TranscriptSegment(1, 2200, 9000, "Let us start the planning meeting."),
        ],
    )


@pytest.fixture
def storage(tmp_path):
    return LocalMeetingVideoStorage(
        tmp_path / "meetings", allowed_extensions=(".mp4", ".wav"), max_bytes=10 * 1024 * 1024
    )


@pytest.fixture
def meeting_with_audio(db, meeting_owner, storage):
    m = Meeting(created_by=meeting_owner, title="Standup", status="pending")
    db.add(m)
    db.flush()
    audio_abs = storage.derived_target(m.id, "audio.wav")
    _write_wav(audio_abs, seconds=2)
    m.audio_path = storage.to_relative(audio_abs)
    db.commit()
    db.refresh(m)
    return m


# --------------------------------------------------------------------------- #
# persistence  (fake transcriber)
# --------------------------------------------------------------------------- #
def test_full_transcript_and_metadata_persisted(db, storage, meeting_with_audio):
    t = service.transcribe_meeting(db, meeting_with_audio.id,
                                   storage=storage, transcriber=fake_transcriber)
    assert t.full_text.startswith("Hello team.")
    assert t.language == "en"
    assert t.whisper_model == "fake-whisper"
    assert t.segment_count == 2
    assert t.word_count == len(t.full_text.split())

    db.expire_all()
    m = db.get(Meeting, meeting_with_audio.id)
    assert m.language == "en"
    assert db.query(MeetingTranscript).filter_by(meeting_id=m.id).count() == 1


def test_segments_have_ms_timestamps_and_null_speaker(db, storage, meeting_with_audio):
    service.transcribe_meeting(db, meeting_with_audio.id,
                               storage=storage, transcriber=fake_transcriber)
    rows = (
        db.query(MeetingTranscriptSegment)
        .filter_by(meeting_id=meeting_with_audio.id)
        .order_by(MeetingTranscriptSegment.seq)
        .all()
    )
    assert [r.seq for r in rows] == [0, 1]
    assert (rows[0].start_ms, rows[0].end_ms) == (0, 2200)
    assert (rows[1].start_ms, rows[1].end_ms) == (2200, 9000)
    assert all(r.end_ms >= r.start_ms for r in rows)
    # Phase 6 not done yet — no speaker attribution
    assert all(r.speaker_id is None and r.speaker_label is None for r in rows)


def test_reprocess_replaces_previous_transcript(db, storage, meeting_with_audio):
    service.transcribe_meeting(db, meeting_with_audio.id,
                               storage=storage, transcriber=fake_transcriber)

    def other(_p):
        return TranscriptionResult(
            text="Completely different.", language="es", language_probability=0.9,
            duration_sec=3.0, model="fake-2",
            segments=[TranscriptSegment(0, 0, 3000, "Completely different.")],
        )

    t2 = service.transcribe_meeting(db, meeting_with_audio.id, storage=storage, transcriber=other)
    assert t2.language == "es"
    assert db.query(MeetingTranscript).filter_by(meeting_id=meeting_with_audio.id).count() == 1
    segs = db.query(MeetingTranscriptSegment).filter_by(meeting_id=meeting_with_audio.id).all()
    assert len(segs) == 1 and segs[0].text == "Completely different."


def test_no_audio_bytes_columns_on_transcript_tables():
    from config.database import engine
    for table in ("meeting_transcripts", "meeting_transcript_segments"):
        cols = inspect(engine).get_columns(table)
        assert not any(str(c["type"]).upper() in ("BYTEA", "BLOB", "OID") for c in cols)


def test_transcript_full_text_is_text_type(db, storage, meeting_with_audio):
    service.transcribe_meeting(db, meeting_with_audio.id,
                               storage=storage, transcriber=fake_transcriber)
    row = db.execute(text(
        "SELECT full_text, pg_typeof(full_text)::text AS ty "
        "FROM meeting_transcripts WHERE meeting_id = :m"
    ), {"m": meeting_with_audio.id}).one()
    assert row.ty == "text" and isinstance(row.full_text, str)


# --------------------------------------------------------------------------- #
# error handling
# --------------------------------------------------------------------------- #
def test_missing_audio_path(db, meeting_owner, storage):
    m = Meeting(created_by=meeting_owner, title="NoAudio", status="pending")
    db.add(m)
    db.commit()
    with pytest.raises(HTTPException) as ei:
        service.transcribe_meeting(db, m.id, storage=storage, transcriber=fake_transcriber)
    assert ei.value.status_code == 422


def test_audio_file_missing_from_storage(db, storage, meeting_with_audio):
    storage.resolve(meeting_with_audio.audio_path).unlink()
    with pytest.raises(HTTPException) as ei:
        service.transcribe_meeting(db, meeting_with_audio.id,
                                   storage=storage, transcriber=fake_transcriber)
    assert ei.value.status_code == 422


def test_transcription_failure_rolls_back(db, storage, meeting_with_audio):
    def boom(_p):
        raise TranscriptionError("model exploded")

    with pytest.raises(HTTPException) as ei:
        service.transcribe_meeting(db, meeting_with_audio.id, storage=storage, transcriber=boom)
    assert ei.value.status_code == 422
    db.rollback()
    assert db.query(MeetingTranscript).filter_by(meeting_id=meeting_with_audio.id).count() == 0


def test_transcribe_audio_missing_file(tmp_path):
    with pytest.raises(AudioNotFoundError):
        transcribe_audio(tmp_path / "nope.wav", model="tiny")


# --------------------------------------------------------------------------- #
# real faster-whisper — offline, CPU, int8
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_faster_whisper_runs_offline_on_cpu(tmp_path):
    wav = tmp_path / "silence.wav"
    _write_wav(wav, seconds=2)
    result = transcribe_audio(wav, model="tiny", device="cpu", compute_type="int8")
    assert result.model == "tiny"
    assert isinstance(result.segments, list)
    assert result.duration_sec == pytest.approx(2, abs=1)
    for s in result.segments:
        assert 0 <= s.start_ms <= s.end_ms


@pytest.mark.slow
@pytest.mark.skipif(platform.system() != "Windows", reason="uses Windows SAPI to synthesise speech")
def test_faster_whisper_transcribes_real_speech(tmp_path):
    speech = tmp_path / "speech.wav"
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SetOutputToWaveFile('{speech}'); $s.Rate = -1; "
        "$s.Speak('The quarterly planning meeting is scheduled for Friday.'); $s.Dispose()"
    )
    proc = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                          capture_output=True, text=True)
    if proc.returncode != 0 or not speech.is_file():
        pytest.skip("SAPI speech synthesis unavailable")

    result = transcribe_audio(speech, model="tiny", device="cpu", compute_type="int8")
    assert result.language == "en"
    assert "friday" in result.text.lower()
    assert result.segments and result.segments[0].end_ms > 0


# --------------------------------------------------------------------------- #
# Gemini transcription provider (used on memory-constrained hosts where
# self-hosted Whisper can't run — mocked here the same way the analysis
# provider's Gemini tests are, see tests/test_meeting_analysis.py).
# --------------------------------------------------------------------------- #
@pytest.fixture
def gemini_provider(monkeypatch):
    import modules.meeting_intelligence.processing.transcription as tmod
    monkeypatch.setattr(tmod.meeting_settings, "transcription_provider", "gemini")
    monkeypatch.setattr(tmod.settings, "GEMINI_API_KEY", "x")
    monkeypatch.setattr(tmod.time, "sleep", lambda *_: None)
    return tmod


def test_gemini_transcription_single_segment_success(tmp_path, gemini_provider, monkeypatch):
    wav = tmp_path / "clip.wav"
    _write_wav(wav, seconds=3)

    class FakeModels:
        def generate_content(self, **_):
            return type("R", (), {"text": "Hello team, let's begin."})()

    class FakeClient:
        def __init__(self, **_):
            self.models = FakeModels()

    monkeypatch.setattr("google.genai.Client", FakeClient)
    result = transcribe_audio(wav)

    assert result.model == "gemini:gemini-flash-lite-latest"
    assert result.text == "Hello team, let's begin."
    assert len(result.segments) == 1
    assert result.segments[0].start_ms == 0
    assert result.segments[0].end_ms == pytest.approx(3000, abs=50)


def test_gemini_transcription_no_speech_returns_empty_segments(tmp_path, gemini_provider, monkeypatch):
    wav = tmp_path / "silence.wav"
    _write_wav(wav, seconds=2)

    class FakeModels:
        def generate_content(self, **_):
            return type("R", (), {"text": "NO_SPEECH"})()

    class FakeClient:
        def __init__(self, **_):
            self.models = FakeModels()

    monkeypatch.setattr("google.genai.Client", FakeClient)
    result = transcribe_audio(wav)

    assert result.text == ""
    assert result.segments == []


def test_gemini_transcription_retries_then_raises(tmp_path, gemini_provider, monkeypatch):
    wav = tmp_path / "clip.wav"
    _write_wav(wav, seconds=1)

    class FakeModels:
        def generate_content(self, **_):
            raise RuntimeError("429 RESOURCE_EXHAUSTED quotaId per-minute")

    class FakeClient:
        def __init__(self, **_):
            self.models = FakeModels()

    monkeypatch.setattr("google.genai.Client", FakeClient)
    with pytest.raises(TranscriptionError):
        transcribe_audio(wav)
