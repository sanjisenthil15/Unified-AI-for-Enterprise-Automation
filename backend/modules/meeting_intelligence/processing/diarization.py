"""
processing/diarization.py — Phase 6.

Speaker diarization: split a meeting's audio into "who spoke when" and label
distinct voices "Speaker 1", "Speaker 2", ... The labels are generic — they
are NOT assumed to be real employees (mapping happens later via the API).

Pluggable by design:

    Diarizer (ABC)
      ├─ ResemblyzerDiarizer   resemblyzer d-vectors + scikit-learn
      │                        AgglomerativeClustering  (default, lightweight)
      ├─ SingleSpeakerDiarizer everything is "Speaker 1"  (fallback)
      └─ (pyannote / other backends can be added here later)

`get_diarizer()` picks the backend from MeetingSettings and transparently
falls back to SingleSpeakerDiarizer when the optional stack
(resemblyzer / torch / librosa) is not installed, so the meeting pipeline
never crashes for a missing optional dependency.

No Gemini, no network, no changes to the audio/video files.
"""

from __future__ import annotations

import warnings
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from modules.meeting_intelligence.config import meeting_settings

FIRST_SPEAKER = "Speaker 1"


class DiarizationError(Exception):
    """A diarization backend failed to process the audio."""


@dataclass(frozen=True)
class SpeakerTurn:
    speaker_label: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class DiarizationResult:
    speaker_labels: list[str]      # distinct, ordered by first appearance
    turns: list[SpeakerTurn]       # contiguous, non-overlapping, time-ordered
    backend: str
    num_speakers: int


def _label(index: int) -> str:
    return f"Speaker {index + 1}"


# --------------------------------------------------------------------------- #
# Interface + trivial backend
# --------------------------------------------------------------------------- #
class Diarizer(ABC):
    name: str = "diarizer"

    @abstractmethod
    def diarize(self, audio_path: str | Path) -> DiarizationResult:
        ...

    def _single(self, total_ms: int) -> DiarizationResult:
        total_ms = max(int(total_ms), 0)
        return DiarizationResult(
            speaker_labels=[FIRST_SPEAKER],
            turns=[SpeakerTurn(FIRST_SPEAKER, 0, total_ms)],
            backend=self.name,
            num_speakers=1,
        )


class SingleSpeakerDiarizer(Diarizer):
    """Assigns the whole meeting to one speaker. Always safe."""

    name = "single"

    def diarize(self, audio_path: str | Path) -> DiarizationResult:
        path = Path(audio_path)
        if not path.is_file():
            raise DiarizationError(f"Audio file not found: {path}")
        total_ms = _probe_duration_ms(path)
        return self._single(total_ms)


# --------------------------------------------------------------------------- #
# Resemblyzer + scikit-learn backend
# --------------------------------------------------------------------------- #
def resemblyzer_available() -> bool:
    """True when the optional diarization stack can be imported."""
    try:
        import librosa  # noqa: F401
        import numpy  # noqa: F401
        import resemblyzer  # noqa: F401
        import sklearn  # noqa: F401
        return True
    except Exception:
        return False


def _probe_duration_ms(path: Path) -> int:
    """Best-effort audio duration in ms (used by the single-speaker path)."""
    try:
        import wave

        with wave.open(str(path), "rb") as w:
            frames, rate = w.getnframes(), w.getframerate()
            if rate:
                return int(frames / rate * 1000)
    except Exception:
        pass
    try:
        import librosa

        return int(librosa.get_duration(path=str(path)) * 1000)
    except Exception:
        return 0


class ResemblyzerDiarizer(Diarizer):
    name = "resemblyzer"

    def __init__(
        self,
        *,
        max_speakers: int | None = None,
        window_sec: float | None = None,
        hop_sec: float | None = None,
        distance_threshold: float | None = None,
        min_cluster_fraction: float = 0.12,
        min_windows: int = 4,
    ) -> None:
        self.max_speakers = max_speakers or meeting_settings.diarization_max_speakers
        self.window_sec = window_sec or meeting_settings.diarization_window_sec
        self.hop_sec = hop_sec or meeting_settings.diarization_hop_sec
        self.distance_threshold = (
            distance_threshold
            if distance_threshold is not None
            else meeting_settings.diarization_distance_threshold
        )
        self.min_cluster_fraction = min_cluster_fraction
        self.min_windows = min_windows
        self._encoder = None

    def _encoder_lazy(self):
        if self._encoder is None:
            from resemblyzer import VoiceEncoder

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self._encoder = VoiceEncoder("cpu", verbose=False)
        return self._encoder

    def diarize(self, audio_path: str | Path) -> DiarizationResult:
        path = Path(audio_path)
        if not path.is_file():
            raise DiarizationError(f"Audio file not found: {path}")

        try:
            import librosa
            import numpy as np

            wav, sr = librosa.load(str(path), sr=16_000, mono=True)
        except Exception as exc:  # noqa: BLE001
            raise DiarizationError(f"Could not load audio: {exc}") from exc

        if wav is None or len(wav) == 0:
            raise DiarizationError("Audio contains no samples.")

        total_ms = int(len(wav) / sr * 1000)
        win = int(self.window_sec * sr)
        hop = max(int(self.hop_sec * sr), 1)
        min_win = int(0.4 * sr)

        windows: list[tuple[int, int]] = []
        i = 0
        while i < len(wav):
            j = min(i + win, len(wav))
            if j - i >= min_win:
                windows.append((i, j))
            if j == len(wav):
                break
            i += hop

        if len(windows) < self.min_windows:
            return self._single(total_ms)

        try:
            encoder = self._encoder_lazy()
            embeds = np.stack([encoder.embed_utterance(wav[a:b]) for a, b in windows])
        except Exception as exc:  # noqa: BLE001
            raise DiarizationError(f"Speaker embedding failed: {exc}") from exc

        try:
            cluster_ids = self._cluster(embeds)
        except Exception as exc:  # noqa: BLE001
            raise DiarizationError(f"Clustering failed: {exc}") from exc

        if cluster_ids is None:
            return self._single(total_ms)

        turns = self._windows_to_turns(windows, cluster_ids, sr, total_ms)
        labels = _ordered_labels(turns)
        return DiarizationResult(
            speaker_labels=labels,
            turns=turns,
            backend=self.name,
            num_speakers=len(labels),
        )

    # -- clustering: distance threshold + small-cluster filter -------- #
    def _cluster(self, embeds):
        """
        Return per-window cluster ids, or None when the audio looks like a
        single speaker.

        Step 1: cluster with a cosine distance_threshold (no fixed k).
        Step 2: keep only clusters holding a meaningful share of windows —
                this drops 1-2 outlier windows that otherwise inflate the
                speaker count.
        Step 3: if >= 2 real clusters remain, re-cluster with that exact k so
                every window (outliers included) lands in a real speaker.
        """
        import numpy as np
        from sklearn.cluster import AgglomerativeClustering

        n = len(embeds)
        if n < self.min_windows:
            return None

        raw = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=self.distance_threshold,
            metric="cosine",
            linkage="average",
        ).fit_predict(embeds)

        sizes = np.bincount(raw)
        min_size = max(2, int(np.ceil(self.min_cluster_fraction * n)))
        real_clusters = int((sizes >= min_size).sum())
        k = min(real_clusters, self.max_speakers)
        if k <= 1:
            return None

        return AgglomerativeClustering(
            n_clusters=k, metric="cosine", linkage="average"
        ).fit_predict(embeds)

    # -- window labels -> contiguous turns --------------------------- #
    @staticmethod
    def _windows_to_turns(windows, cluster_ids, sr, total_ms) -> list[SpeakerTurn]:
        chunk_ms = 250  # resolution of turn boundaries
        n_chunks = max((total_ms + chunk_ms - 1) // chunk_ms, 1)

        votes: list[dict[int, int]] = [dict() for _ in range(n_chunks)]
        for (a, b), cid in zip(windows, cluster_ids):
            c0 = int(a / sr * 1000) // chunk_ms
            c1 = int(b / sr * 1000) // chunk_ms
            for c in range(c0, min(c1 + 1, n_chunks)):
                votes[c][int(cid)] = votes[c].get(int(cid), 0) + 1

        chunk_label: list[int] = []
        last = int(cluster_ids[0])
        for v in votes:
            if v:
                last = max(v, key=v.get)
            chunk_label.append(last)

        turns: list[SpeakerTurn] = []
        run_start = 0
        for idx in range(1, n_chunks + 1):
            if idx == n_chunks or chunk_label[idx] != chunk_label[run_start]:
                s = run_start * chunk_ms
                e = min(idx * chunk_ms, total_ms)
                if e > s:
                    turns.append(SpeakerTurn(f"__c{chunk_label[run_start]}", s, e))
                run_start = idx
        return turns or [SpeakerTurn("__c0", 0, total_ms)]


def _ordered_labels(turns: list[SpeakerTurn]) -> list[str]:
    """Rename placeholder cluster tags to Speaker N by first appearance, in place."""
    mapping: dict[str, str] = {}
    for turn in turns:
        if turn.speaker_label not in mapping:
            mapping[turn.speaker_label] = _label(len(mapping))
    # rebuild turns list content (frozen dataclass -> replace)
    for i, turn in enumerate(turns):
        turns[i] = SpeakerTurn(mapping[turn.speaker_label], turn.start_ms, turn.end_ms)
    return list(dict.fromkeys(t.speaker_label for t in turns))


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
def get_diarizer(backend: str | None = None) -> Diarizer:
    """
    Return the configured diarizer. Falls back to SingleSpeakerDiarizer when
    the requested backend's optional dependencies are unavailable.
    """
    backend = (backend or meeting_settings.diarization_backend or "resemblyzer").lower()

    if backend == "single":
        return SingleSpeakerDiarizer()

    if backend == "resemblyzer":
        if resemblyzer_available():
            return ResemblyzerDiarizer()
        warnings.warn(
            "Diarization stack (resemblyzer/torch) not installed — "
            "falling back to single-speaker mode.",
            RuntimeWarning,
            stacklevel=2,
        )
        return SingleSpeakerDiarizer()

    # Unknown / not-yet-implemented backend (e.g. "pyannote")
    warnings.warn(f"Unknown diarization backend {backend!r} — using single-speaker mode.",
                  RuntimeWarning, stacklevel=2)
    return SingleSpeakerDiarizer()
