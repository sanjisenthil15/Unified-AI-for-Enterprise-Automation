"""
processing/audio.py — Phase 4.

Extract audio from a meeting video for offline speech-to-text.

Uses the FFmpeg binary bundled by `imageio-ffmpeg`, so no system FFmpeg is
required. Produces a mono PCM WAV at the configured sample rate (16 kHz by
default — what faster-whisper expects).

This module is pure media processing: it takes explicit source/target paths
and knows nothing about the database or the storage backend. Orchestration
(reading the meeting row, writing `audio_path`) lives in service.py.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg

_DURATION_RE = re.compile(r"Duration:\s+(\d+):(\d+):(\d+(?:\.\d+)?)")


class AudioExtractionError(Exception):
    """Raised when audio could not be extracted from a source video."""


@dataclass(frozen=True)
class AudioInfo:
    path: Path
    sample_rate: int
    channels: int
    duration_sec: int
    size_bytes: int


def _cleanup(path: Path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _parse_duration(stderr: str) -> int | None:
    m = _DURATION_RE.search(stderr or "")
    if not m:
        return None
    hours, minutes, seconds = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return round(hours * 3600 + minutes * 60 + seconds)


def _duration_from_pcm(size_bytes: int, sample_rate: int, channels: int) -> int:
    # PCM s16le -> 2 bytes/sample; subtract a nominal 44-byte WAV header.
    data = max(size_bytes - 44, 0)
    return round(data / (sample_rate * channels * 2)) if sample_rate and channels else 0


def get_ffmpeg_exe() -> str:
    """Absolute path to the bundled FFmpeg binary."""
    return imageio_ffmpeg.get_ffmpeg_exe()


def extract_audio(
    source_video: Path | str,
    target_audio: Path | str,
    *,
    sample_rate: int = 16_000,
    channels: int = 1,
    timeout: float | None = 3600,
) -> AudioInfo:
    """
    Extract audio from `source_video` into `target_audio` (a WAV path).

    The source video is only read, never modified. On any failure the target
    file is removed so no partial audio is left behind, and
    AudioExtractionError is raised.
    """
    source = Path(source_video)
    target = Path(target_audio)

    if not source.is_file():
        raise AudioExtractionError(f"Source video not found: {source}")

    target.parent.mkdir(parents=True, exist_ok=True)
    _cleanup(target)  # start clean

    cmd = [
        get_ffmpeg_exe(),
        "-nostdin", "-y",
        "-i", str(source),
        "-vn",                       # drop video
        "-acodec", "pcm_s16le",
        "-ar", str(sample_rate),
        "-ac", str(channels),
        str(target),
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _cleanup(target)
        raise AudioExtractionError(f"FFmpeg timed out after {timeout}s") from exc
    except OSError as exc:
        _cleanup(target)
        raise AudioExtractionError(f"Could not run FFmpeg: {exc}") from exc

    ok = proc.returncode == 0 and target.is_file() and target.stat().st_size > 44
    if not ok:
        _cleanup(target)
        tail = " / ".join((proc.stderr or "").strip().splitlines()[-12:])
        raise AudioExtractionError(f"FFmpeg failed (exit {proc.returncode}): {tail}")

    size = target.stat().st_size
    duration = _parse_duration(proc.stderr) or _duration_from_pcm(size, sample_rate, channels)
    return AudioInfo(
        path=target,
        sample_rate=sample_rate,
        channels=channels,
        duration_sec=duration,
        size_bytes=size,
    )
