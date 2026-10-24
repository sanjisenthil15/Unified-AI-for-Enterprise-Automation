"""
modules/meeting_intelligence/router.py — Phase 8.

HTTP surface for Meeting Intelligence. All routes require a valid JWT
(core.dependencies.get_current_user) and are scoped to the caller's own
meetings — a meeting owned by another user is reported as 404.

    POST   /api/v1/meetings                     upload a recorded meeting
    GET    /api/v1/meetings                     the caller's meeting history
    GET    /api/v1/meetings/{id}                details + processing status
    GET    /api/v1/meetings/{id}/transcript     transcript + speakers + segments
    GET    /api/v1/meetings/{id}/analysis       summary / key points / decisions
    GET    /api/v1/meetings/{id}/action-items   extracted action items
    DELETE /api/v1/meetings/{id}                delete the meeting + its files

Processing (audio -> transcription -> diarization -> analysis) runs in a
FastAPI background task; the upload returns immediately with the meeting id
and status so the frontend can poll GET /meetings/{id}.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from config.database import get_db
from core.dependencies import get_current_employee_optional, get_current_user
from models.employee import Employee
from models.user import User
from modules.meeting_intelligence import service
from modules.meeting_intelligence.pipeline import run_meeting_pipeline
from modules.meeting_intelligence.schemas import (
    ActionItemOut,
    AnalysisResponse,
    AssignActionItem,
    ConvertActionItem,
    MeetingListItem,
    MeetingResponse,
    ScheduledMeetingOut,
    ScheduleMeetingCreate,
    SpeakerOut,
    TranscriptResponse,
    TranscriptSegmentOut,
)
from modules.meeting_intelligence.storage import MeetingVideoStorage, get_storage

router = APIRouter(prefix="/meetings", tags=["Meeting Intelligence"])


def storage_dependency() -> MeetingVideoStorage:
    """Indirection so tests can override the storage backend."""
    return get_storage()


@router.post(
    "",
    response_model=MeetingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a recorded meeting and start offline processing",
)
async def upload_meeting(
    background_tasks: BackgroundTasks,
    title: str = Form(..., min_length=1, max_length=255),
    description: Optional[str] = Form(None, max_length=4000),
    meeting_date: Optional[datetime] = Form(None),
    project_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: MeetingVideoStorage = Depends(storage_dependency),
):
    meeting = service.create_meeting(
        db,
        created_by=current_user.id,
        upload_file=file,
        title=title,
        description=description,
        meeting_date=meeting_date,
        project_id=project_id,
        storage=storage,
    )
    background_tasks.add_task(run_meeting_pipeline, meeting.id)
    return meeting


@router.get("", response_model=List[MeetingListItem], summary="Meeting history (own meetings)")
def list_meetings(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.list_meetings(db, current_user.id, skip=skip, limit=limit)


@router.post(
    "/schedule",
    response_model=ScheduledMeetingOut,
    status_code=status.HTTP_201_CREATED,
    summary="Book a future meeting for a project team (invites + notifies every member)",
)
def schedule_meeting(
    payload: ScheduleMeetingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    meeting = service.schedule_meeting(
        db,
        organizer=current_user,
        organizer_employee=current_employee,
        title=payload.title,
        description=payload.description,
        project_id=payload.project_id,
        scheduled_at=payload.scheduled_at,
    )
    return _scheduled_meeting_out(meeting)


@router.get(
    "/scheduled",
    response_model=List[ScheduledMeetingOut],
    summary="Upcoming scheduled meetings the caller organized or was invited to",
)
def list_scheduled(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    meetings = service.list_scheduled_meetings(db, current_user, current_employee)
    return [_scheduled_meeting_out(m) for m in meetings]


def _scheduled_meeting_out(meeting) -> ScheduledMeetingOut:
    return ScheduledMeetingOut(
        id=meeting.id,
        title=meeting.title,
        description=meeting.description,
        project_id=meeting.project_id,
        project_name=meeting.project.name if meeting.project else "—",
        organizer_user_id=meeting.created_by,
        organizer_name=meeting.creator.full_name if meeting.creator else "—",
        scheduled_at=meeting.scheduled_at,
        invitee_count=len(meeting.participants),
        created_at=meeting.created_at,
    )


@router.get("/{meeting_id}", response_model=MeetingResponse, summary="Meeting details + status")
def get_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return service.get_owned_meeting(db, meeting_id, current_user.id)


@router.get(
    "/{meeting_id}/transcript",
    response_model=TranscriptResponse,
    summary="Full transcript, speakers and diarized segments",
)
def get_transcript(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service.get_owned_meeting(db, meeting_id, current_user.id)
    transcript = service.get_meeting_transcript(db, meeting_id)
    return TranscriptResponse(
        meeting_id=meeting_id,
        language=transcript.language,
        whisper_model=transcript.whisper_model,
        word_count=transcript.word_count,
        segment_count=transcript.segment_count,
        full_text=transcript.full_text,
        speakers=[SpeakerOut.model_validate(s) for s in service.list_meeting_speakers(db, meeting_id)],
        segments=[TranscriptSegmentOut.model_validate(s) for s in service.list_meeting_segments(db, meeting_id)],
    )


@router.get(
    "/{meeting_id}/analysis",
    response_model=AnalysisResponse,
    summary="Summary, key discussion points and decisions",
)
def get_analysis(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service.get_owned_meeting(db, meeting_id, current_user.id)
    analysis = service.get_meeting_analysis(db, meeting_id)
    return AnalysisResponse(
        meeting_id=meeting_id,
        summary=analysis.summary,
        key_points=analysis.key_points or [],
        decisions=analysis.decisions or [],
        sentiment=analysis.sentiment,
        model_provider=analysis.model_provider,
        model_name=analysis.model_name,
        generated_at=analysis.generated_at,
    )


@router.get(
    "/{meeting_id}/action-items",
    response_model=List[ActionItemOut],
    summary="AI-extracted action items",
)
def get_action_items(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service.get_owned_meeting(db, meeting_id, current_user.id)
    return service.list_meeting_action_items(db, meeting_id)


@router.patch(
    "/{meeting_id}/action-items/{action_item_id}/assign",
    response_model=ActionItemOut,
    summary="Manually assign (or unassign) an action item to a registered user",
)
def assign_action_item(
    meeting_id: int,
    action_item_id: int,
    payload: AssignActionItem,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service.get_owned_meeting(db, meeting_id, current_user.id)
    return service.assign_action_item(db, meeting_id, action_item_id, payload.assigned_to_user_id)


@router.post(
    "/{meeting_id}/action-items/{action_item_id}/convert",
    response_model=ActionItemOut,
    summary="Convert an action item into an assigned Sprint task",
)
def convert_action_item(
    meeting_id: int,
    action_item_id: int,
    payload: ConvertActionItem,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_employee: Optional[Employee] = Depends(get_current_employee_optional),
):
    meeting = service.get_owned_meeting(db, meeting_id, current_user.id)
    return service.convert_action_item_to_task(
        db, current_user, current_employee, meeting, action_item_id,
        payload.sprint_id, payload.assignee_id, payload.due_date,
    )


@router.post(
    "/{meeting_id}/reprocess",
    response_model=MeetingResponse,
    summary="Re-run processing for a failed/completed meeting (resumes from the failed stage)",
)
def reprocess_meeting(
    meeting_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    meeting = service.get_owned_meeting(db, meeting_id, current_user.id)
    if meeting.status not in ("failed", "completed"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Meeting is '{meeting.status}' — wait for the current run to finish.",
        )
    meeting.status = "pending"
    meeting.error_message = None
    db.commit()
    db.refresh(meeting)
    background_tasks.add_task(run_meeting_pipeline, meeting.id, resume=True)
    return meeting


@router.delete(
    "/{meeting_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a meeting and its stored files",
)
def delete_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: MeetingVideoStorage = Depends(storage_dependency),
):
    service.get_owned_meeting(db, meeting_id, current_user.id)
    service.delete_meeting(db, meeting_id, storage=storage)
