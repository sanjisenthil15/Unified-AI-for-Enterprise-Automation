"""Small adapters around the existing offline module's pure processors.

Independent browser clips are decoded into temporary WAV files. Nothing is
written to offline meeting storage or PostgreSQL. Providers run off the event loop.
"""

import base64
import binascii
import threading
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

from modules.meeting_intelligence.config import meeting_settings
from modules.meeting_intelligence.processing.analysis import get_analysis_provider
from modules.meeting_intelligence.processing.audio import extract_audio
from modules.meeting_intelligence.processing.transcription import transcribe_audio
from modules.meeting_online.schemas import ActionItemResult, LiveAnalysisResult

# Serialize calls into the reused CPU model. Do not create a model per clip.
_TRANSCRIPTION_LOCK = threading.Lock()
_EXTENSIONS = {
    "audio/webm": ".webm", "audio/ogg": ".ogg",
    "audio/mp4": ".mp4", "audio/wav": ".wav",
}


def transcribe_chunk(data: str, mime_type: str):
    try:
        audio = base64.b64decode(data, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("Audio must be valid base64.") from exc
    if not audio or len(audio) > 2_000_000:
        raise ValueError("Audio must contain 1 to 2,000,000 bytes.")
    if mime_type not in _EXTENSIONS:
        raise ValueError("Unsupported audio format.")
    with TemporaryDirectory(prefix="meeting-online-") as directory:
        source = Path(directory) / ("clip" + _EXTENSIONS[mime_type])
        target = Path(directory) / "normalized.wav"
        source.write_bytes(audio)
        extract_audio(source, target, timeout=20)
        with wave.open(str(target), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
        if duration > 31:
            raise ValueError("Audio clips must not exceed 30 seconds.")
        with _TRANSCRIPTION_LOCK:
            return transcribe_audio(target)


def analyze_transcript(segments):
    text = "\n".join(f"{segment.speaker}: {segment.text}" for segment in segments)
    # The service rejects excess transcript length, rather than silently dropping
    # early decisions from the provider's context.
    if len(text) > meeting_settings.analysis_max_transcript_chars:
        raise ValueError("Transcript exceeds the configured analysis limit.")
    result = get_analysis_provider().analyze(text)
    return LiveAnalysisResult(
        summary=result.summary,
        key_points=result.key_points,
        decisions=result.decisions,
        action_items=[
            ActionItemResult(
                description=item.description,
                assignee=item.assignee_name_raw,
                priority=item.priority,
                confidence=item.confidence,
            ) for item in result.action_items
        ],
        model_provider=result.model_provider,
        model_name=result.model_name,
        transcript_count=len(segments),
    )