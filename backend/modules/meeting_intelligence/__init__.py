"""
Meeting Intelligence — OFFLINE meeting processing module.

Owns the offline pipeline:
    recorded video -> audio extraction -> offline transcription (faster-whisper)
    -> speaker diarization (resemblyzer + clustering, pluggable)
    -> AI analysis (Gemini via google-genai, provider-abstracted)
    -> summary / key points / decisions / action items
    -> persistence in PostgreSQL (video stays on disk, only its path is stored)
    -> meeting history

The online / live meeting phase is a separate module owned by another
developer and is NOT touched here.

Build phases (each lands as its own commit):
    1. Foundation      — module skeleton + dependencies + config   [THIS COMMIT]
    2. Database        — ORM models + Alembic migration
    3. Video handling  — upload + local storage
    4. Audio extraction — imageio-ffmpeg
    5. Transcription   — faster-whisper (offline)
    6. Diarization     — resemblyzer + scikit-learn clustering
    7. AI analysis     — Gemini structured output
    8. Meeting API     — router endpoints + pipeline orchestration
    9. Testing         — end-to-end with a short sample clip
"""
