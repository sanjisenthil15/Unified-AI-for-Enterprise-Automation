"""
modules/meeting_intelligence/config.py

Module-local configuration. Kept separate from the global config/settings.py
so Meeting Intelligence stays self-contained; all keys are optional and read
from the same .env file using the ``MEETING_`` prefix.

Example .env entries (all optional):
    MEETING_STORAGE_DIR=uploads/meetings
    MEETING_WHISPER_MODEL=base
    MEETING_WHISPER_DEVICE=cpu
    MEETING_WHISPER_COMPUTE_TYPE=int8
    MEETING_DIARIZATION_BACKEND=resemblyzer
    MEETING_AI_PROVIDER=gemini
    MEETING_GEMINI_MODEL=gemini-3.6-flash
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class MeetingSettings(BaseSettings):
    # --- storage ---------------------------------------------------------- #
    # Relative paths are resolved against the backend/ directory.
    storage_dir: str = "uploads/meetings"
    max_upload_mb: int = 1024
    allowed_video_extensions: tuple[str, ...] = (
        ".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v",
        ".mp3", ".wav", ".m4a", ".aac", ".flac",
    )

    # --- audio extraction (imageio-ffmpeg) ----------------------------- #
    audio_sample_rate: int = 16_000      # 16 kHz mono is what faster-whisper expects
    audio_channels: int = 1
    audio_filename: str = "audio.wav"

    # --- offline transcription (faster-whisper) -------------------------- #
    whisper_model: str = "base"          # tiny | base | small | medium | large-v3
    whisper_device: str = "cpu"          # cpu | cuda
    whisper_compute_type: str = "int8"   # int8 | int8_float16 | float16 | float32
    whisper_language: str | None = None  # None => auto-detect
    whisper_beam_size: int = 1           # 1 is fastest on CPU

    # --- speaker diarization (pluggable) -------------------------------- #
    diarization_backend: str = "resemblyzer"   # resemblyzer | pyannote | single
    diarization_max_speakers: int = 8
    diarization_window_sec: float = 1.5
    diarization_hop_sec: float = 0.75
    diarization_distance_threshold: float = 0.35   # cosine; higher => fewer speakers

    # --- AI analysis (pluggable provider) ------------------------------ #
    ai_provider: str = "gemini"                # gemini | ollama
    gemini_model: str = "gemini-3.6-flash"     # matches the Recruitment module

    model_config = SettingsConfigDict(
        env_prefix="MEETING_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def storage_path(self) -> Path:
        """Absolute path to the meeting upload directory (backend/uploads/meetings)."""
        p = Path(self.storage_dir)
        if not p.is_absolute():
            p = Path(__file__).resolve().parents[2] / p
        return p


meeting_settings = MeetingSettings()
