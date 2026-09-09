"""
modules/meeting_intelligence/pipeline.py

Runs the offline processing stages in order and advances the Meeting status:

    pending -> extracting_audio -> transcribing -> diarizing -> analyzing
            -> completed              (or -> failed, with error_message)

Populated in Phase 8. Executed via FastAPI BackgroundTasks for the MVP
(no Celery/Redis in the project). Each stage is delegated to ``processing/``.
"""
