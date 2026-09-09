"""
modules/meeting_intelligence/processing/

Isolated processing stages for the offline meeting pipeline. Each file owns
exactly one responsibility and is called only by pipeline.py:

    audio.py          extract audio from the uploaded video (imageio-ffmpeg)
    transcription.py  offline speech-to-text (faster-whisper)
    diarization.py    speaker segmentation + labels (resemblyzer + clustering),
                      behind a pluggable interface so pyannote can replace it;
                      falls back to a single "Speaker 1" if it fails
    merge.py          align transcription segments with diarization turns
    analysis.py       transcript -> structured JSON (summary, key points,
                      decisions, action items) via a provider abstraction
                      (Gemini now, Ollama possible later)

All of these are stubs in Phase 1 — no implementation yet.
"""
