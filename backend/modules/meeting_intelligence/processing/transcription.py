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

import time
import wave
from dataclasses import dataclass
from pathlib import Path

from config.settings import settings
from modules.meeting_intelligence.config import meeting_settings
from modules.meeting_intelligence.processing.analysis import _RETRY_DELAY_RE, _is_retryable


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
    Transcribe a WAV file into timestamped segments.

    Dispatches on meeting_settings.transcription_provider:
      - "whisper" (default): self-hosted faster-whisper. Needs real CPU/RAM.
      - "gemini": sends the clip to the Gemini API instead — no heavy model
        runs in-process, for hosts too memory-constrained to run Whisper.

    Timestamps are milliseconds. Raises AudioNotFoundError if the file is
    missing, TranscriptionError on any backend failure.
    """
    path = Path(audio_path)
    if not path.is_file():
        raise AudioNotFoundError(str(path))

    if meeting_settings.transcription_provider == "gemini":
        return _transcribe_with_gemini(path, language)
    return _transcribe_with_whisper(path, model, device, compute_type, language, beam_size)


def _transcribe_with_whisper(
    path: Path,
    model: str | None,
    device: str | None,
    compute_type: str | None,
    language: str | None,
    beam_size: int | None,
) -> TranscriptionResult:
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


_GEMINI_PROMPT = (
    "Transcribe the spoken words in this audio clip exactly, in the language "
    "spoken. Respond with exactly NO_SPEECH if there is no speech in it. "
    "Otherwise return only the transcript text — no commentary, no quotes, "
    "no timestamps."
)


def _wav_duration_sec(path: Path) -> float | None:
    try:
        with wave.open(str(path), "rb") as wav:
            return wav.getnframes() / wav.getframerate()
    except (wave.Error, EOFError, OSError):
        return None


def _transcribe_with_gemini(path: Path, language: str | None) -> TranscriptionResult:
    if not settings.GEMINI_API_KEY or not settings.GEMINI_API_KEY.strip():
        raise TranscriptionError("GEMINI_API_KEY is not configured.")

    audio_bytes = path.read_bytes()
    model = meeting_settings.gemini_model
    attempt = 0
    while True:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            response = client.models.generate_content(
                model=model,
                contents=[
                    _GEMINI_PROMPT,
                    types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
                ],
            )
            text = (getattr(response, "text", "") or "").strip()
            break
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if attempt < meeting_settings.gemini_max_retries and _is_retryable(message):
                attempt += 1
                m = _RETRY_DELAY_RE.search(message)
                delay = min(float(m.group(1)) if m else 5.0, 20.0)
                time.sleep(delay)
                continue
            raise TranscriptionError(f"Gemini transcription failed: {exc}") from exc

    duration_sec = _wav_duration_sec(path)
    duration_ms = int(round((duration_sec or 0) * 1000))
    segments: list[TranscriptSegment] = []
    if text and text != "NO_SPEECH":
        segments.append(TranscriptSegment(seq=0, start_ms=0, end_ms=duration_ms, text=text))

    return TranscriptionResult(
        text=text if text != "NO_SPEECH" else "",
        language=language or meeting_settings.whisper_language,
        language_probability=None,
        duration_sec=duration_sec,
        model=f"gemini:{model}",
        segments=segments,
    )
