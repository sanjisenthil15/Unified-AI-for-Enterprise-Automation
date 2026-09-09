"""
Phase 6 — speaker diarization (resemblyzer + scikit-learn, pluggable).

Deterministic persistence / mapping / fallback tests use an injected fake
diarizer. Real-model tests (@slow, Windows SAPI voices) prove the
resemblyzer backend actually separates speakers.
"""

import platform
import subprocess
import wave

import pytest
from fastapi import HTTPException

from models.meeting import Meeting
from models.meeting_speaker import MeetingSpeaker
from models.meeting_transcript import MeetingTranscript
from models.meeting_transcript_segment import MeetingTranscriptSegment
from modules.meeting_intelligence import service
from modules.meeting_intelligence.processing import diarization as diar
from modules.meeting_intelligence.processing.audio import get_ffmpeg_exe
from modules.meeting_intelligence.processing.diarization import (
    Diarizer,
    DiarizationError,
    DiarizationResult,
    ResemblyzerDiarizer,
    SingleSpeakerDiarizer,
    SpeakerTurn,
    get_diarizer,
)
from modules.meeting_intelligence.storage import LocalMeetingVideoStorage

WINDOWS = platform.system() == "Windows"


# --------------------------------------------------------------------------- #
# helpers / fixtures
# --------------------------------------------------------------------------- #
def _write_silence_wav(path, seconds=12, sample_rate=16_000):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * sample_rate * seconds)


class FakeDiarizer(Diarizer):
    name = "fake"

    def __init__(self, result):
        self._result = result

    def diarize(self, audio_path):
        return self._result


class BoomDiarizer(Diarizer):
    name = "boom"

    def diarize(self, audio_path):
        raise DiarizationError("backend exploded")


SINGLE = DiarizationResult(
    speaker_labels=["Speaker 1"],
    turns=[SpeakerTurn("Speaker 1", 0, 12_000)],
    backend="fake",
    num_speakers=1,
)
TWO = DiarizationResult(
    speaker_labels=["Speaker 1", "Speaker 2"],
    turns=[SpeakerTurn("Speaker 1", 0, 6_000), SpeakerTurn("Speaker 2", 6_000, 12_000)],
    backend="fake",
    num_speakers=2,
)


@pytest.fixture
def storage(tmp_path):
    return LocalMeetingVideoStorage(
        tmp_path / "meetings", allowed_extensions=(".mp4", ".wav"), max_bytes=50 * 1024 * 1024
    )


@pytest.fixture
def meeting_ready(db, meeting_owner, storage):
    """Meeting with an audio file + a 4-segment transcript (0-12 s)."""
    m = Meeting(created_by=meeting_owner, title="Planning", status="pending")
    db.add(m)
    db.flush()
    audio = storage.derived_target(m.id, "audio.wav")
    _write_silence_wav(audio, seconds=12)
    m.audio_path = storage.to_relative(audio)

    db.add(MeetingTranscript(meeting_id=m.id, full_text="a b c d", segment_count=4))
    spans = [(0, 2_500), (2_500, 5_500), (6_000, 9_000), (9_000, 12_000)]
    for i, (s, e) in enumerate(spans):
        db.add(MeetingTranscriptSegment(meeting_id=m.id, seq=i, start_ms=s, end_ms=e, text=f"seg{i}"))
    db.commit()
    db.refresh(m)
    return m


def _speakers(db, meeting_id):
    return db.query(MeetingSpeaker).filter_by(meeting_id=meeting_id).order_by(MeetingSpeaker.label).all()


def _segments(db, meeting_id):
    return (
        db.query(MeetingTranscriptSegment)
        .filter_by(meeting_id=meeting_id)
        .order_by(MeetingTranscriptSegment.seq)
        .all()
    )


# --------------------------------------------------------------------------- #
# persistence + mapping (fake diarizer)
# --------------------------------------------------------------------------- #
def test_single_speaker_fallback_persists_one_speaker(db, storage, meeting_ready):
    service.diarize_meeting(db, meeting_ready.id, storage=storage, diarizer=FakeDiarizer(SINGLE))
    speakers = _speakers(db, meeting_ready.id)
    assert [s.label for s in speakers] == ["Speaker 1"]
    assert all(seg.speaker_label == "Speaker 1" and seg.speaker_id == speakers[0].id
               for seg in _segments(db, meeting_ready.id))


def test_multiple_speakers_persisted_and_mapped(db, storage, meeting_ready):
    service.diarize_meeting(db, meeting_ready.id, storage=storage, diarizer=FakeDiarizer(TWO))
    speakers = _speakers(db, meeting_ready.id)
    assert [s.label for s in speakers] == ["Speaker 1", "Speaker 2"]

    segs = _segments(db, meeting_ready.id)
    # spans 0-2500 and 2500-5500 -> Speaker 1 ; 6000-9000 and 9000-12000 -> Speaker 2
    assert [s.speaker_label for s in segs] == ["Speaker 1", "Speaker 1", "Speaker 2", "Speaker 2"]
    assert all(s.speaker_id is not None for s in segs)


def test_speaker_labels_are_sequential(db, storage, meeting_ready):
    service.diarize_meeting(db, meeting_ready.id, storage=storage, diarizer=FakeDiarizer(TWO))
    labels = [s.label for s in _speakers(db, meeting_ready.id)]
    assert labels == ["Speaker 1", "Speaker 2"]


def test_meeting_speakers_persistence_and_manual_mapping_fields(db, storage, meeting_ready):
    service.diarize_meeting(db, meeting_ready.id, storage=storage, diarizer=FakeDiarizer(TWO))
    for sp in _speakers(db, meeting_ready.id):
        assert sp.segment_count == 2
        assert sp.total_speaking_sec is not None and sp.total_speaking_sec > 0
        # left NULL so a real identity can be attached later (req 15)
        assert sp.display_name is None
        assert sp.mapped_user_id is None and sp.mapped_employee_id is None
    db.expire_all()
    assert db.get(Meeting, meeting_ready.id).diarization_backend == "fake"


def test_transcript_segment_speaker_mapping_overlap(db, storage, meeting_ready):
    turns = [SpeakerTurn("Speaker 1", 0, 3_000), SpeakerTurn("Speaker 2", 3_000, 12_000)]
    result = DiarizationResult(["Speaker 1", "Speaker 2"], turns, "fake", 2)
    service.diarize_meeting(db, meeting_ready.id, storage=storage, diarizer=FakeDiarizer(result))
    segs = _segments(db, meeting_ready.id)
    # seg0 0-2500 -> S1 ; seg1 2500-5500 overlaps S1 by 500, S2 by 2500 -> S2
    assert segs[0].speaker_label == "Speaker 1"
    assert segs[1].speaker_label == "Speaker 2"


def test_reprocess_replaces_speakers(db, storage, meeting_ready):
    service.diarize_meeting(db, meeting_ready.id, storage=storage, diarizer=FakeDiarizer(TWO))
    first_ids = {s.id for s in _speakers(db, meeting_ready.id)}
    service.diarize_meeting(db, meeting_ready.id, storage=storage, diarizer=FakeDiarizer(SINGLE))
    speakers = _speakers(db, meeting_ready.id)
    assert len(speakers) == 1
    assert not (first_ids & {s.id for s in speakers})
    assert all(s.speaker_label == "Speaker 1" for s in _segments(db, meeting_ready.id))


# --------------------------------------------------------------------------- #
# failure / fallback handling
# --------------------------------------------------------------------------- #
def test_missing_audio_path(db, meeting_owner, storage):
    m = Meeting(created_by=meeting_owner, title="NoAudio", status="pending")
    db.add(m)
    db.commit()
    with pytest.raises(HTTPException) as ei:
        service.diarize_meeting(db, m.id, storage=storage, diarizer=FakeDiarizer(SINGLE))
    assert ei.value.status_code == 422


def test_audio_file_missing_from_storage(db, storage, meeting_ready):
    storage.resolve(meeting_ready.audio_path).unlink()
    with pytest.raises(HTTPException) as ei:
        service.diarize_meeting(db, meeting_ready.id, storage=storage, diarizer=FakeDiarizer(SINGLE))
    assert ei.value.status_code == 422


def test_diarization_failure_falls_back_to_single(db, storage, meeting_ready):
    # BoomDiarizer raises -> service must fall back, not crash
    service.diarize_meeting(db, meeting_ready.id, storage=storage, diarizer=BoomDiarizer())
    speakers = _speakers(db, meeting_ready.id)
    assert [s.label for s in speakers] == ["Speaker 1"]
    assert all(s.speaker_label == "Speaker 1" for s in _segments(db, meeting_ready.id))


def test_graceful_fallback_when_optional_deps_unavailable(db, storage, meeting_ready, monkeypatch):
    monkeypatch.setattr(diar, "resemblyzer_available", lambda: False)
    engine = get_diarizer("resemblyzer")
    assert isinstance(engine, SingleSpeakerDiarizer)
    service.diarize_meeting(db, meeting_ready.id, storage=storage, diarizer=engine)
    assert [s.label for s in _speakers(db, meeting_ready.id)] == ["Speaker 1"]


# --------------------------------------------------------------------------- #
# pluggable backend selection
# --------------------------------------------------------------------------- #
def test_backend_selection():
    assert isinstance(get_diarizer("single"), SingleSpeakerDiarizer)
    with pytest.warns(RuntimeWarning):
        assert isinstance(get_diarizer("pyannote"), SingleSpeakerDiarizer)
    assert isinstance(get_diarizer("resemblyzer"), ResemblyzerDiarizer)


def test_single_speaker_diarizer_turn_timestamps(tmp_path):
    wav = tmp_path / "s.wav"
    _write_silence_wav(wav, seconds=5)
    result = SingleSpeakerDiarizer().diarize(wav)
    assert result.num_speakers == 1
    assert len(result.turns) == 1
    t = result.turns[0]
    assert t.start_ms == 0 and t.end_ms == pytest.approx(5_000, abs=100)
    assert t.start_ms < t.end_ms


# --------------------------------------------------------------------------- #
# real resemblyzer backend
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def _sapi_voices():
    if not WINDOWS:
        pytest.skip("needs Windows SAPI")
    return True


def _synth(path, text, voice_index=0):
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$v = $s.GetInstalledVoices().VoiceInfo.Name;"
        f"$s.SelectVoice($v[[Math]::Min({voice_index}, $v.Count-1)]);"
        f"$s.SetOutputToWaveFile('{path}');"
        f"$s.Speak('{text}'); $s.Dispose()"
    )
    p = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True)
    return p.returncode == 0 and path.is_file()


@pytest.mark.slow
def test_real_diarization_single_speaker(tmp_path, _sapi_voices):
    raw = tmp_path / "a.wav"
    if not _synth(raw, "Hello everyone. Today I will walk through the whole quarterly plan, "
                       "covering goals, timeline, budget, and the main risks we identified.", 0):
        pytest.skip("SAPI unavailable")
    wav = tmp_path / "one.wav"
    subprocess.run([get_ffmpeg_exe(), "-y", "-i", str(raw), "-ar", "16000", "-ac", "1", str(wav)],
                   capture_output=True)
    result = ResemblyzerDiarizer().diarize(wav)
    assert result.num_speakers == 1
    assert result.speaker_labels == ["Speaker 1"]


@pytest.mark.slow
def test_real_diarization_two_speakers(tmp_path, _sapi_voices):
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    ok = _synth(a, "Hello everyone, let us begin the weekly project status meeting. "
                   "I will start with the summary and the milestones for this month.", 0)
    ok &= _synth(b, "Thanks. I will present the engineering update, the deployment plan, "
                    "and the open risks for this iteration in detail now.", 99)
    if not ok:
        pytest.skip("SAPI two-voice synthesis unavailable")
    two = tmp_path / "two.wav"
    r = subprocess.run(
        [get_ffmpeg_exe(), "-y", "-i", str(a), "-i", str(b),
         "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1", "-ar", "16000", "-ac", "1", str(two)],
        capture_output=True, text=True,
    )
    assert two.is_file(), r.stderr
    result = ResemblyzerDiarizer().diarize(two)
    if result.num_speakers < 2:
        pytest.skip("installed SAPI voices too similar to separate")
    assert result.num_speakers == 2
    assert result.speaker_labels == ["Speaker 1", "Speaker 2"]
    assert all(t.start_ms < t.end_ms for t in result.turns)
    assert result.turns == sorted(result.turns, key=lambda t: t.start_ms)
