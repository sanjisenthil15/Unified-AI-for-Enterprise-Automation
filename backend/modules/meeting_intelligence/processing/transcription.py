"""
processing/transcription.py — Phase 5.

Completely offline speech-to-text with faster-whisper.

The model runs on CPU by default (see MeetingSettings) so it works in the
college development environment with no GPU. The model files are downloaded
once on first use and cached by faster-whisper (~/.cache/huggingface).

This module is pure processing: it takes an audio path and returns
timestamped segments. It knows nothing about the database, speakers, or
diarization (speaker attribution is Phase 6).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from modules.meeting_intelligence.config import meeting_settings


class TranscriptionError(Exception):
    """Raised when transcription could not be produced."""


class AudioNotFoundError(TranscriptionError, FileNotFoundError):
    """The audio file to transcribe does not exist."""


@dataclass(frozen=True)
class TranscriptSegment:
    seq: int
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    language: str | None
    language_probability: float | None
    duration_sec: float | None
    model: str
    segments: list[TranscriptSegment]


# One loaded model per (name, device, compute_type) — loading is expensive.
_MODEL_CACHE: dict[tuple[str, str, str], object] = {}


def _get_model(model: str, device: str, compute_type: str):
    key = (model, device, compute_type)
    cached = _MODEL_CACHE.get(key)
    if cached is None:
        from faster_whisper import WhisperModel  # imported lazily — heavy

        cached = WhisperModel(model, device=device, compute_type=compute_type)
        _MODEL_CACHE[key] = cached
    return cached


def transcribe_audio(
    audio_path: Path | str,
    *,
    model: str | None = None,
    device: str | None = None,
    compute_type: str | None = None,
    language: str | None = None,
    beam_size: int | None = None,
) -> TranscriptionResult:
    """
    Transcribe a WAV file into timestamped segments (offline).

    Timestamps are milliseconds. Raises AudioNotFoundError if the file is
    missing, TranscriptionError on any model/decoding failure.
    """
    path = Path(audio_path)
    if not path.is_file():
        raise AudioNotFoundError(str(path))

    model = model or meeting_settings.whisper_model
    device = device or meeting_settings.whisper_device
    compute_type = compute_type or meeting_settings.whisper_compute_type
    language = language if language is not None else meeting_settings.whisper_language
    beam_size = beam_size or meeting_settings.whisper_beam_size

    try:
        whisper_model = _get_model(model, device, compute_type)
        segment_iter, info = whisper_model.transcribe(
            str(path), language=language, beam_size=beam_size,
        )
        segments: list[TranscriptSegment] = []
        parts: list[str] = []
        for index, seg in enumerate(segment_iter):  # generator — consume it
            text = (seg.text or "").strip()
            segments.append(TranscriptSegment(
                seq=index,
                start_ms=max(int(round(seg.start * 1000)), 0),
                end_ms=max(int(round(seg.end * 1000)), 0),
                text=text,
            ))
            if text:
                parts.append(text)
    except AudioNotFoundError:
        raise
    except Exception as exc:  # noqa: BLE001 — normalise every backend failure
        raise TranscriptionError(f"faster-whisper failed: {exc}") from exc

    return TranscriptionResult(
        text=" ".join(parts).strip(),
        language=getattr(info, "language", None),
        language_probability=getattr(info, "language_probability", None),
        duration_sec=getattr(info, "duration", None),
        model=model,
        segments=segments,
    )
