"""
processing/merge.py — Phase 6.

Attribute each transcribed segment to the diarization speaker whose turn
overlaps it most. Pure function, no DB.
"""

from __future__ import annotations

from collections.abc import Sequence

from modules.meeting_intelligence.processing.diarization import SpeakerTurn


def label_for_span(
    start_ms: int,
    end_ms: int,
    turns: Sequence[SpeakerTurn],
    *,
    default: str | None = None,
) -> str | None:
    """
    Return the speaker label whose turn overlaps [start_ms, end_ms] the most.

    Falls back to the nearest turn by gap, then to `default` (or the first
    turn's label) when there are turns but none overlap.
    """
    if not turns:
        return default

    best_label, best_overlap = None, 0
    for turn in turns:
        overlap = min(end_ms, turn.end_ms) - max(start_ms, turn.start_ms)
        if overlap > best_overlap:
            best_overlap, best_label = overlap, turn.speaker_label

    if best_label is not None:
        return best_label

    # no overlap — pick the temporally closest turn
    mid = (start_ms + end_ms) / 2
    nearest = min(
        turns,
        key=lambda t: 0 if t.start_ms <= mid <= t.end_ms else min(abs(mid - t.start_ms), abs(mid - t.end_ms)),
    )
    return nearest.speaker_label or default or turns[0].speaker_label
