"""
modules/meeting_intelligence/service.py

Persistence + retrieval logic for Meeting Intelligence (thin orchestration
layer, following the Recruitment module's structure).

Populated from Phase 3 onward. Responsibilities:
    - create a Meeting row from an upload and hand off to the pipeline
    - read back meetings, transcripts, analyses, action items
    - manual action-item assignment and speaker -> person mapping
    - dashboard stats

No AI or media processing lives here — that is in ``processing/`` and is
driven by ``pipeline.py``.
"""
