"""
modules/meeting_intelligence/router.py

FastAPI router for Meeting Intelligence.

Phase 1 (foundation) defines the router object only — it carries no routes
yet and is intentionally NOT registered in backend/main.py. Endpoints and
their registration land in Phase 8 (Meeting API):

    POST   /api/v1/meetings                         upload video + metadata
    GET    /api/v1/meetings                         list / history
    GET    /api/v1/meetings/{id}                    detail + processing status
    GET    /api/v1/meetings/{id}/transcript         diarized transcript
    GET    /api/v1/meetings/{id}/analysis           summary / key points / decisions
    GET    /api/v1/meetings/{id}/action-items       extracted action items
    PUT    /api/v1/meetings/{id}/action-items/{aid} manual assignment (MVP)
    PUT    /api/v1/meetings/{id}/speakers/{sid}     map "Speaker N" -> employee/user
    POST   /api/v1/meetings/{id}/participants       add participants manually
    POST   /api/v1/meetings/{id}/reprocess          re-run the pipeline
    DELETE /api/v1/meetings/{id}                    delete meeting + files
    GET    /api/v1/meetings/stats                   dashboard counters
"""

from fastapi import APIRouter

router = APIRouter(prefix="/meetings", tags=["Meeting Intelligence"])
