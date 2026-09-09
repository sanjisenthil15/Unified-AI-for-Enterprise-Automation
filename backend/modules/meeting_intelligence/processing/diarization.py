"""
processing/diarization.py — Phase 6.

Speaker diarization behind a pluggable interface:

    class Diarizer(Protocol):
        def diarize(self, wav_path: str) -> list[SpeakerTurn]: ...

Planned backends (selected by MeetingSettings.diarization_backend):
    "resemblyzer" — resemblyzer voice embeddings + scikit-learn
                    AgglomerativeClustering over VAD windows  (default)
    "pyannote"    — drop-in upgrade, added later
    "single"      — no diarization; everything is "Speaker 1"

Speaker labels stay generic ("Speaker 1", "Speaker 2", ...) — they are NOT
assumed to be real employees. Mapping to employees/users happens later via
the API. If diarization raises, the pipeline falls back to "single".

The "resemblyzer" backend needs the optional stack in backend/requirements-ml.txt
(torch, resemblyzer). When it is not installed, this module must degrade to the
"single" backend rather than error.

Stub only in Phase 1.
"""
