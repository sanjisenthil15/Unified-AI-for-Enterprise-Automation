"""
modules/meeting_intelligence/service.py

Persistence + retrieval logic for Meeting Intelligence.

Phase 3 implements meeting creation (video upload -> disk + DB row) and
deletion. Transcription / diarization / AI analysis and their orchestration
are added in later phases via pipeline.py; nothing here starts processing.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Callable
from types import SimpleNamespace

if TYPE_CHECKING:
    from modules.meeting_online.schemas import OnlineMeetingSession

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.authorization import (
    assert_can_link_project_meeting,
    assert_can_review_action_items,
    assert_can_view_meeting,
)
from modules.notifications.service import create_notification
from modules.sprints import service as sprints_service

from core.permissions import OVERRIDE_ROLES
from models.employee import Employee
from models.meeting import Meeting
from models.meeting_action_item import MeetingActionItem
from models.meeting_analysis import MeetingAnalysis
from models.meeting_participant import MeetingParticipant
from models.meeting_speaker import MeetingSpeaker
from models.meeting_transcript import MeetingTranscript
from models.meeting_transcript_segment import MeetingTranscriptSegment
from models.project import Project
from models.user import User
from modules.meeting_intelligence.config import meeting_settings
from modules.meeting_intelligence.processing.analysis import (
    AnalysisError,
    AnalysisProvider,
    AnalysisResult,
    get_analysis_provider,
)
from modules.meeting_intelligence.processing.audio import AudioExtractionError, extract_audio
from modules.meeting_intelligence.processing.diarization import (
    Diarizer,
    DiarizationError,
    SingleSpeakerDiarizer,
    get_diarizer,
)
from modules.meeting_intelligence.processing.merge import label_for_span
from modules.meeting_intelligence.processing.transcription import (
    TranscriptionError,
    TranscriptionResult,
    transcribe_audio,
)
from modules.meeting_intelligence.storage import (
    EmptyUploadError,
    FileTooLargeError,
    MeetingVideoStorage,
    StorageError,
    StorageUnavailableError,
    UnsupportedMediaError,
    get_storage,
)

# A transcriber takes an audio path and returns a TranscriptionResult.
Transcriber = Callable[[str], TranscriptionResult]


def create_meeting(
    db: Session,
    *,
    created_by: int,
    upload_file: UploadFile,
    title: str,
    description: str | None = None,
    meeting_date: datetime | None = None,
    project_id: int | None = None,
    storage: MeetingVideoStorage | None = None,
) -> Meeting:
    """
    Create a meeting from an uploaded video.

    Flow: insert the row (to get an id) -> stream the file to storage ->
    record the path reference -> commit. The video bytes never touch the DB.
    On any storage failure nothing is committed and no partial file remains.
    """
    storage = storage or get_storage()

    if not title or not title.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A meeting title is required.")

    meeting = Meeting(
        created_by=created_by,
        title=title.strip(),
        description=description,
        meeting_date=meeting_date,
        project_id=project_id,
        status="pending",
    )
    db.add(meeting)
    db.flush()  # assigns meeting.id, no commit yet
    meeting_id = meeting.id

    try:
        stored = storage.save_video(
            meeting_id,
            fileobj=upload_file.file,
            original_filename=upload_file.filename or "",
            content_type=upload_file.content_type,
        )
    except UnsupportedMediaError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc))
    except FileTooLargeError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(exc))
    except StorageUnavailableError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    except (EmptyUploadError, StorageError) as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    meeting.source_video_path     = stored.relative_path
    meeting.source_video_filename = stored.original_filename
    meeting.source_media_type     = stored.content_type
    meeting.file_size_bytes       = stored.size_bytes

    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete_meeting_files(meeting_id)
        raise
    db.refresh(meeting)
    return meeting


def schedule_meeting(
    db: Session,
    *,
    organizer: User,
    organizer_employee: Employee | None,
    title: str,
    description: str | None,
    project_id: int,
    scheduled_at: datetime,
) -> Meeting:
    """Books a future meeting for a project team. Every current member of
    that project is invited (as a MeetingParticipant) and notified.
    Starting an Online Meeting against this booking later fills in the
    same row with a transcript/analysis/action items — see
    create_or_update_meeting_from_online_session — so it ends up in the
    same offline history and action-item-conversion flow as an uploaded
    recording, no separate "scheduled meetings" data model to reconcile."""
    from core.authorization import assert_project_manager
    from modules.notifications.service import create_notification

    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Project id={project_id} not found.")
    assert_project_manager(db, organizer, organizer_employee, project_id)

    if not title or not title.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A meeting title is required.")

    meeting = Meeting(
        created_by=organizer.id,
        title=title.strip(),
        description=description,
        project_id=project_id,
        scheduled_at=scheduled_at,
        status="scheduled",
    )
    db.add(meeting)
    db.flush()  # assigns meeting.id

    members = (
        db.query(Employee)
        .filter(Employee.project_id == project_id, Employee.deleted_at.is_(None))
        .all()
    )
    member_user_ids = {m.user_id for m in members if m.user_id}
    notify_user_ids: set[int] = set()
    for member in members:
        db.add(MeetingParticipant(
            meeting_id=meeting.id,
            user_id=member.user_id,
            employee_id=member.id,
            display_name=member.user.full_name if member.user else f"Employee #{member.id}",
            role="organizer" if member.user_id == organizer.id else "attendee",
        ))
        if member.user_id and member.user_id != organizer.id:
            notify_user_ids.add(member.user_id)

    if organizer.id not in member_user_ids:
        db.add(MeetingParticipant(
            meeting_id=meeting.id,
            user_id=organizer.id,
            employee_id=organizer_employee.id if organizer_employee else None,
            display_name=organizer.full_name,
            role="organizer",
        ))

    db.commit()
    db.refresh(meeting)

    for user_id in notify_user_ids:
        create_notification(
            db, user_id, "meeting",
            f"{organizer.full_name} scheduled '{meeting.title}' for {scheduled_at:%b %d, %I:%M %p}.",
            "/meetings/scheduled",
        )
    return meeting


def list_scheduled_meetings(db: Session, current_user: User, current_employee: Employee | None) -> list[Meeting]:
    """Upcoming (status='scheduled') meetings visible to the caller:
    admin/hr_manager/manager see every scheduled meeting; everyone else sees only
    ones they organized or were invited to."""
    query = db.query(Meeting).filter(Meeting.status == "scheduled")
    role = getattr(current_user, "role", None)
    role_name = getattr(role, "name", role)
    if role_name not in OVERRIDE_ROLES:
        invited_ids = db.query(MeetingParticipant.meeting_id).filter(
            MeetingParticipant.user_id == current_user.id
        )
        query = query.filter((Meeting.created_by == current_user.id) | Meeting.id.in_(invited_ids))
    return query.order_by(Meeting.scheduled_at.asc()).all()



def create_or_update_meeting_from_online_session(
    db: Session,
    *,
    owner_id: int,
    session: "OnlineMeetingSession",
    project_id: int | None,
    linked_meeting_id: int | None,
) -> int:
    """Called once a live Online Meeting ends (see
    modules/meeting_online/service.py's _end()) so the session stops being
    in-memory-only (previously discarded 24h after ending) and shows up in
    the same offline Meeting Intelligence history, transcript viewer and
    action-item-to-Sprint-task conversion flow as an uploaded recording.

    If `linked_meeting_id` points at a meeting this same user scheduled,
    that row is filled in in place (status scheduled -> completed);
    otherwise a new ad-hoc Meeting row is created."""
    meeting = None
    if linked_meeting_id is not None:
        meeting = (
            db.query(Meeting)
            .filter(Meeting.id == linked_meeting_id, Meeting.created_by == owner_id)
            .first()
        )

    if meeting is None:
        meeting = Meeting(created_by=owner_id, title=session.title, project_id=project_id)
        db.add(meeting)
    else:
        meeting.title = session.title
        if project_id is not None:
            meeting.project_id = project_id

    meeting.meeting_date = session.started_at
    if session.started_at and session.ended_at:
        meeting.duration_sec = max(0, int((session.ended_at - session.started_at).total_seconds()))
    meeting.status = "completed"
    db.flush()  # assigns meeting.id for a new row

    # Online participants are identified by display name; those who
    # authenticated through the ws ticket also carry a user_id (see
    # meeting_online's join()), which we resolve to an Employee here the
    # same way an uploaded meeting's participants would be. Upsert by
    # user_id rather than blind-insert: a linked scheduled meeting already
    # has one MeetingParticipant row per invited project member (including
    # the organizer), and the same person reconnecting mid-session gets a
    # new client_id each time — both would otherwise collide with
    # uq_meeting_participant_user.
    existing_by_user = {
        p.user_id: p for p in
        db.query(MeetingParticipant)
        .filter(MeetingParticipant.meeting_id == meeting.id, MeetingParticipant.user_id.isnot(None))
        .all()
    }
    seen_user_ids: set[int] = set()
    for participant in session.participants:
        if participant.user_id is not None:
            if participant.user_id in seen_user_ids:
                continue
            seen_user_ids.add(participant.user_id)
        existing = existing_by_user.get(participant.user_id) if participant.user_id is not None else None
        if existing is not None:
            existing.display_name = participant.speaker[:255]
            if participant.user_id == owner_id:
                existing.role = "organizer"
            continue
        employee = None
        if participant.user_id:
            employee = db.query(Employee).filter(Employee.user_id == participant.user_id).first()
        db.add(MeetingParticipant(
            meeting_id=meeting.id,
            user_id=participant.user_id,
            employee_id=employee.id if employee else None,
            display_name=participant.speaker[:255],
            role="organizer" if participant.user_id == owner_id else "attendee",
        ))

    if session.transcript:
        full_text = "\n".join(
            f"{seg.speaker}: {seg.text}".strip() for seg in session.transcript if seg.text.strip()
        ) or "(no transcript text)"
        db.add(MeetingTranscript(
            meeting_id=meeting.id,
            full_text=full_text,
            word_count=len(full_text.split()),
            segment_count=len(session.transcript),
        ))
        for index, seg in enumerate(session.transcript):
            db.add(MeetingTranscriptSegment(
                meeting_id=meeting.id,
                speaker_label=(seg.speaker or "")[:50],
                seq=index,
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
                text=seg.text,
            ))

    if session.analysis:
        analysis = MeetingAnalysis(
            meeting_id=meeting.id,
            summary=session.analysis.summary,
            key_points=session.analysis.key_points or None,
            decisions=session.analysis.decisions or None,
            model_provider=session.analysis.model_provider or "gemini",
            model_name=session.analysis.model_name or None,
        )
        db.add(analysis)
        db.flush()  # assigns analysis.id
        for item in session.analysis.action_items:
            db.add(MeetingActionItem(
                meeting_id=meeting.id,
                analysis_id=analysis.id,
                description=item.description,
                assignee_name_raw=item.assignee,
                assignment_method="unassigned",
                priority=item.priority,
                status="pending",
                review_status="proposed",
                is_legacy_conversion=False,
                source="ai",
                ai_confidence=item.confidence,
            ))

    db.commit()
    return meeting.id


def get_meeting(db: Session, meeting_id: int) -> Meeting:
    """Fetch a meeting or raise 404."""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Meeting id={meeting_id} not found.")
    return meeting


def recover_orphaned_meetings(db: Session) -> int:
    """
    Called once at process startup. A meeting stuck in "pending"/"processing"
    can only mean its background task died with the previous process (that
    status only exists while a task is actively running in-memory) — mark it
    failed so "Retry processing" (which only accepts failed/completed) can
    recover it, instead of leaving it stranded forever. Returns the count
    recovered.
    """
    stuck = db.query(Meeting).filter(Meeting.status.in_(("pending", "processing"))).all()
    for meeting in stuck:
        meeting.status = "failed"
        meeting.error_message = "Processing was interrupted by a server restart. Click Retry to try again."
    if stuck:
        db.commit()
    return len(stuck)


def get_owned_meeting(db: Session, meeting_id: int, user_id: int) -> Meeting:
    """
    Fetch a meeting that belongs to `user_id`. A meeting owned by someone else
    is reported as 404 (never reveal that it exists).
    """
    meeting = (
        db.query(Meeting)
        .filter(Meeting.id == meeting_id, Meeting.created_by == user_id)
        .first()
    )
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Meeting id={meeting_id} not found.")
    return meeting


def list_meetings(
    db: Session,
    user_or_id: User | int,
    current_employee: Employee | None = None,
    *,
    skip: int = 0,
    limit: int = 50,
) -> list[Meeting]:
    """Meeting history filtered by caller's permissions, newest first."""
    if isinstance(user_or_id, int):
        current_user = db.query(User).filter(User.id == user_or_id).first()
        if current_user is None:
            return []
    else:
        current_user = user_or_id

    role_name = getattr(current_user.role, "name", None) if hasattr(current_user, "role") else None

    if role_name == "admin":
        # Admin sees own unlinked meetings + all project-linked meetings
        query = db.query(Meeting).filter(
            or_(
                Meeting.created_by == current_user.id,
                Meeting.project_id.isnot(None),
            )
        )
    else:
        allowed_project_ids: set[int] = set()
        if role_name == "manager":
            mgr_pids = db.query(Project.id).filter(Project.manager_user_id == current_user.id).all()
            allowed_project_ids.update(p[0] for p in mgr_pids)

        if current_employee is None:
            current_employee = db.query(Employee).filter(Employee.user_id == current_user.id).first()

        if current_employee is not None:
            tl_pids = db.query(Project.id).filter(Project.team_lead_id == current_employee.id).all()
            allowed_project_ids.update(p[0] for p in tl_pids)
            if current_employee.project_id is not None:
                allowed_project_ids.add(current_employee.project_id)

        if allowed_project_ids:
            query = db.query(Meeting).filter(
                or_(
                    Meeting.created_by == current_user.id,
                    Meeting.project_id.in_(allowed_project_ids),
                )
            )
        else:
            query = db.query(Meeting).filter(Meeting.created_by == current_user.id)

    return (
        query.order_by(Meeting.created_at.desc(), Meeting.id.desc())
        .offset(max(skip, 0))
        .limit(min(max(limit, 1), 200))
        .all()
    )


def get_meeting_transcript(db: Session, meeting_id: int) -> MeetingTranscript:
    transcript = (
        db.query(MeetingTranscript)
        .filter(MeetingTranscript.meeting_id == meeting_id)
        .first()
    )
    if transcript is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transcript is not available yet.")
    return transcript


def list_meeting_segments(db: Session, meeting_id: int) -> list[MeetingTranscriptSegment]:
    return (
        db.query(MeetingTranscriptSegment)
        .filter(MeetingTranscriptSegment.meeting_id == meeting_id)
        .order_by(MeetingTranscriptSegment.seq)
        .all()
    )


def list_meeting_speakers(db: Session, meeting_id: int) -> list[MeetingSpeaker]:
    return (
        db.query(MeetingSpeaker)
        .filter(MeetingSpeaker.meeting_id == meeting_id)
        .order_by(MeetingSpeaker.label)
        .all()
    )


def get_meeting_analysis(db: Session, meeting_id: int) -> MeetingAnalysis:
    analysis = (
        db.query(MeetingAnalysis)
        .filter(MeetingAnalysis.meeting_id == meeting_id)
        .first()
    )
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis is not available yet.")
    return analysis


def list_meeting_action_items(db: Session, meeting_id: int) -> list[MeetingActionItem]:
    return (
        db.query(MeetingActionItem)
        .filter(MeetingActionItem.meeting_id == meeting_id)
        .order_by(MeetingActionItem.id)
        .all()
    )


def assign_action_item(
    db: Session, meeting_id: int, action_item_id: int, assigned_to_user_id: int | None,
) -> MeetingActionItem:
    """Manually assign (or clear) an action item's owner. Caller must already
    have verified the meeting via get_owned_meeting."""
    item = (
        db.query(MeetingActionItem)
        .filter(MeetingActionItem.id == action_item_id, MeetingActionItem.meeting_id == meeting_id)
        .first()
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Action item id={action_item_id} not found.")
    if assigned_to_user_id is not None:
        if db.query(User.id).filter(User.id == assigned_to_user_id, User.deleted_at.is_(None)).first() is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"User id={assigned_to_user_id} does not exist.")
    item.assigned_to_user_id = assigned_to_user_id
    item.assignment_method = "manual" if assigned_to_user_id is not None else "unassigned"
    db.commit()
    db.refresh(item)
    return item


def confirm_action_item(
    db: Session,
    current_user: User,
    current_employee: Employee | None,
    meeting: Meeting,
    action_item_id: int,
    assignee_id: int,
    due_date: date,
    final_description: str | None = None,
) -> MeetingActionItem:
    """
    Approves an action item: sets assignee, deadline, optional final description,
    advances status from proposed to confirmed, and records human reviewer attribution.
    """
    assert_can_review_action_items(db, meeting, current_user, current_employee)

    item = (
        db.query(MeetingActionItem)
        .filter(MeetingActionItem.id == action_item_id, MeetingActionItem.meeting_id == meeting.id)
        .with_for_update()
        .first()
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Action item id={action_item_id} not found.")

    if item.review_status != "proposed":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot confirm action item in '{item.review_status}' status; only 'proposed' items can be confirmed.",
        )

    assignee = db.query(Employee).filter(
        Employee.id == assignee_id,
        Employee.deleted_at.is_(None),
    ).first()
    if assignee is None or assignee.project_id != meeting.project_id or assignee.status != "active":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "assignee_id must be an active member of this meeting's project.",
        )

    if due_date is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "due_date is required to confirm an action item.",
        )

    item.assigned_to_employee_id = assignee.id
    item.assigned_to_user_id = assignee.user_id
    item.assignment_method = "manual"
    item.due_date = due_date
    clean_desc = final_description.strip() if final_description and final_description.strip() else item.description
    item.final_description = clean_desc
    item.review_status = "confirmed"
    item.reviewed_by_id = current_user.id
    item.reviewed_at = datetime.now(timezone.utc)
    item.rejection_reason = None

    db.commit()
    db.refresh(item)
    return item


def reject_action_item(
    db: Session,
    current_user: User,
    current_employee: Employee | None,
    meeting: Meeting,
    action_item_id: int,
    rejection_reason: str,
) -> MeetingActionItem:
    """
    Rejects a proposed action item with a mandatory non-empty reason and records reviewer attribution.
    Terminal state.
    """
    assert_can_review_action_items(db, meeting, current_user, current_employee)

    item = (
        db.query(MeetingActionItem)
        .filter(MeetingActionItem.id == action_item_id, MeetingActionItem.meeting_id == meeting.id)
        .with_for_update()
        .first()
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Action item id={action_item_id} not found.")

    if item.review_status != "proposed":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cannot reject action item in '{item.review_status}' status; only 'proposed' items can be rejected.",
        )

    if not rejection_reason or not rejection_reason.strip():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "rejection_reason is required and cannot be empty.",
        )

    item.review_status = "rejected"
    item.rejection_reason = rejection_reason.strip()
    item.reviewed_by_id = current_user.id
    item.reviewed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(item)
    return item


def convert_action_item_to_task(
    db: Session,
    current_user: User,
    current_employee: Employee | None,
    meeting: Meeting,
    action_item_id: int,
    sprint_id: int,
    assignee_id: int | None = None,
    due_date: date | None = None,
) -> MeetingActionItem:
    """
    Converts a confirmed action item into a Sprint task atomically in a single transaction.
    """
    assert_can_review_action_items(db, meeting, current_user, current_employee)

    if meeting.project_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Cannot convert action items for a meeting not linked to a project.",
        )

    # Acquire parent Project FOR SHARE lock FIRST before locking child rows
    project = sprints_service._get_project_with_share_lock(db, meeting.project_id)
    sprints_service._assert_project_active(project)

    item = (
        db.query(MeetingActionItem)
        .filter(MeetingActionItem.id == action_item_id, MeetingActionItem.meeting_id == meeting.id)
        .with_for_update()
        .first()
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Action item id={action_item_id} not found.")

    if item.review_status == "converted" or item.converted_sprint_task_id is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This action item has already been converted into a Sprint task.",
        )

    if item.review_status != "confirmed":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Only 'confirmed' action items can be converted into sprint tasks (current: '{item.review_status}').",
        )

    target_assignee_id = assignee_id or item.assigned_to_employee_id
    target_due_date = due_date or item.due_date

    if target_assignee_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Action item must have an assignee before conversion.",
        )
    if target_due_date is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Action item must have a due date before conversion.",
        )

    task_desc = item.final_description or item.description
    task_title = task_desc[:200]
    task_payload = SimpleNamespace(
        title=task_title,
        description=task_desc,
        assignee_id=target_assignee_id,
        due_date=target_due_date,
    )

    task, sprint, assignee = sprints_service._create_task_without_commit(
        db=db,
        current_user=current_user,
        current_employee=current_employee,
        sprint_id=sprint_id,
        payload=task_payload,
        validate_project_id=meeting.project_id,
    )

    item.converted_sprint_task_id = task.id
    item.review_status = "converted"
    item.assigned_to_employee_id = target_assignee_id
    if assignee:
        item.assigned_to_user_id = assignee.user_id
    item.due_date = target_due_date
    if item.reviewed_by_id is None:
        item.reviewed_by_id = current_user.id
    if item.reviewed_at is None:
        item.reviewed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(item)

    if assignee is not None:
        try:
            create_notification(
                db, assignee.user_id, "task_assigned",
                f"You were assigned '{task.title}' in sprint '{sprint.name}'.",
                f"/sprints?project_id={sprint.project_id}",
            )
        except Exception:
            pass

    return item


def transcribe_meeting(
    db: Session,
    meeting_id: int,
    *,
    storage: MeetingVideoStorage | None = None,
    transcriber: Transcriber | None = None,
) -> MeetingTranscript:
    """
    Run offline speech-to-text on a meeting's extracted audio and persist the
    result: the full transcript in `meeting_transcripts` and each timestamped
    segment (ms) in `meeting_transcript_segments`.

    Speaker attribution is NOT done here — every segment is stored with
    speaker_id / speaker_label = NULL (diarization is Phase 6).

    Re-running replaces any previous transcript + segments for the meeting.
    Raises HTTP 422 if there is no extracted audio, the audio file is missing,
    or transcription fails.
    """
    storage = storage or get_storage()
    run = transcriber or transcribe_audio
    meeting = get_meeting(db, meeting_id)

    if not meeting.audio_path:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Meeting has no extracted audio. Run audio extraction first.")
    try:
        audio = storage.resolve(meeting.audio_path)
    except StorageError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if not audio.is_file():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Audio file is missing from storage.")

    try:
        result: TranscriptionResult = run(str(audio))
    except TranscriptionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Transcription failed: {exc}")

    # Reprocess-safe: drop any existing transcript + segments first.
    db.query(MeetingTranscriptSegment).filter(
        MeetingTranscriptSegment.meeting_id == meeting_id
    ).delete(synchronize_session=False)
    old = db.query(MeetingTranscript).filter(
        MeetingTranscript.meeting_id == meeting_id
    ).first()
    if old is not None:
        db.delete(old)
        db.flush()

    transcript = MeetingTranscript(
        meeting_id=meeting_id,
        full_text=result.text,
        language=result.language,
        whisper_model=result.model,
        word_count=len(result.text.split()),
        segment_count=len(result.segments),
    )
    db.add(transcript)
    for seg in result.segments:
        db.add(MeetingTranscriptSegment(
            meeting_id=meeting_id,
            speaker_id=None,        # diarization is Phase 6
            speaker_label=None,
            seq=seg.seq,
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            text=seg.text,
        ))

    if result.language:
        meeting.language = result.language
    if not meeting.whisper_model:
        meeting.whisper_model = result.model

    db.commit()
    db.refresh(transcript)
    return transcript


def diarize_meeting(
    db: Session,
    meeting_id: int,
    *,
    storage: MeetingVideoStorage | None = None,
    diarizer: Diarizer | None = None,
) -> list[MeetingSpeaker]:
    """
    Run speaker diarization on the meeting's audio, persist the detected
    speakers in `meeting_speakers`, and attach speaker_id / speaker_label to
    each transcript segment by time overlap.

    Speaker labels are generic ("Speaker 1", ...). The rows keep
    display_name / mapped_user_id / mapped_employee_id NULL so a real
    identity can be attached later via the API — no schema change needed.

    Graceful degradation (req 8): if the diarization backend fails or its
    optional dependencies are missing, this falls back to a single
    "Speaker 1" rather than raising. A genuinely missing/invalid audio file
    still raises HTTP 422.

    Re-running replaces the previous speakers and re-maps the segments.
    Pipeline status transitions are not done here.
    """
    storage = storage or get_storage()
    meeting = get_meeting(db, meeting_id)

    if not meeting.audio_path:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Meeting has no extracted audio. Run audio extraction first.")
    try:
        audio = storage.resolve(meeting.audio_path)
    except StorageError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if not audio.is_file():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Audio file is missing from storage.")

    engine = diarizer or get_diarizer()
    try:
        result = engine.diarize(str(audio))
    except DiarizationError:
        try:
            result = SingleSpeakerDiarizer().diarize(str(audio))
        except DiarizationError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"Diarization failed: {exc}")

    if not result.speaker_labels:
        result = SingleSpeakerDiarizer().diarize(str(audio))

    # Reprocess-safe: clear previous mapping + speakers.
    db.query(MeetingTranscriptSegment).filter(
        MeetingTranscriptSegment.meeting_id == meeting_id
    ).update({"speaker_id": None, "speaker_label": None}, synchronize_session=False)
    db.query(MeetingSpeaker).filter(
        MeetingSpeaker.meeting_id == meeting_id
    ).delete(synchronize_session=False)
    db.flush()

    speakers: dict[str, MeetingSpeaker] = {}
    for label in result.speaker_labels:
        row = MeetingSpeaker(meeting_id=meeting_id, label=label)
        db.add(row)
        speakers[label] = row
    db.flush()

    segments = (
        db.query(MeetingTranscriptSegment)
        .filter(MeetingTranscriptSegment.meeting_id == meeting_id)
        .order_by(MeetingTranscriptSegment.seq)
        .all()
    )
    default_label = result.speaker_labels[0]
    seg_counts: dict[str, int] = {}
    speaking_ms: dict[str, int] = {}
    for seg in segments:
        label = label_for_span(seg.start_ms, seg.end_ms, result.turns, default=default_label)
        if label not in speakers:
            label = default_label
        seg.speaker_id = speakers[label].id
        seg.speaker_label = label
        seg_counts[label] = seg_counts.get(label, 0) + 1
        speaking_ms[label] = speaking_ms.get(label, 0) + max(seg.end_ms - seg.start_ms, 0)

    for label, row in speakers.items():
        row.segment_count = seg_counts.get(label, 0)
        secs = round(speaking_ms.get(label, 0) / 1000)
        row.total_speaking_sec = secs or None

    meeting.diarization_backend = result.backend
    db.commit()
    for row in speakers.values():
        db.refresh(row)
    return list(speakers.values())


def _transcript_text_for_analysis(db: Session, meeting_id: int, transcript: MeetingTranscript) -> str:
    """Diarized transcript ("Speaker N: ...") when segments exist, else the full text."""
    segments = (
        db.query(MeetingTranscriptSegment)
        .filter(MeetingTranscriptSegment.meeting_id == meeting_id)
        .order_by(MeetingTranscriptSegment.seq)
        .all()
    )
    if segments:
        text = "\n".join(
            f"{seg.speaker_label or 'Speaker'}: {seg.text}".strip()
            for seg in segments
            if (seg.text or "").strip()
        )
    else:
        text = transcript.full_text or ""
    limit = meeting_settings.analysis_max_transcript_chars
    return text[:limit]


def analyze_meeting(
    db: Session,
    meeting_id: int,
    *,
    provider: AnalysisProvider | None = None,
) -> MeetingAnalysis:
    """
    Run AI analysis on a meeting's transcript and persist structured output:
    summary + key points + decisions in `meeting_analyses`, and each extracted
    task as a `meeting_action_items` row.

    Action items are created UNASSIGNED (assignment_method='unassigned',
    assigned_to_* NULL). The assignee the AI heard is kept as free text in
    `assignee_name_raw` — a human assigns the real person later. No automatic
    assignment.

    Re-running replaces the analysis and any AI action items a human has not
    touched; manually assigned / edited items are kept.

    HTTP 422 if there is no transcript, 503 if the provider is not configured,
    502 on a provider/parse error. Nothing is persisted on failure.
    """
    engine = provider or get_analysis_provider()
    meeting = get_meeting(db, meeting_id)

    transcript = (
        db.query(MeetingTranscript)
        .filter(MeetingTranscript.meeting_id == meeting_id)
        .first()
    )
    if transcript is None or not (transcript.full_text or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Meeting has no transcript. Run transcription first.")

    text = _transcript_text_for_analysis(db, meeting_id, transcript)
    try:
        result: AnalysisResult = engine.analyze(text)
    except AnalysisError as exc:
        code = (
            status.HTTP_503_SERVICE_UNAVAILABLE if exc.kind == "config"
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(code, f"Meeting analysis failed: {exc}")

    # Reprocess-safe: drop untouched proposed AI action items + the old analysis.
    # Confirmed, rejected, and converted items are never deleted.
    db.query(MeetingActionItem).filter(
        MeetingActionItem.meeting_id == meeting_id,
        MeetingActionItem.source == "ai",
        MeetingActionItem.assignment_method == "unassigned",
        MeetingActionItem.review_status == "proposed",
        MeetingActionItem.reviewed_by_id.is_(None),
    ).delete(synchronize_session=False)
    old = db.query(MeetingAnalysis).filter(
        MeetingAnalysis.meeting_id == meeting_id
    ).first()
    if old is not None:
        db.delete(old)
        db.flush()

    analysis = MeetingAnalysis(
        meeting_id=meeting_id,
        summary=result.summary,
        key_points=result.key_points or None,
        decisions=result.decisions or None,
        sentiment=result.sentiment,
        model_provider=result.model_provider,
        model_name=result.model_name or None,
        raw_response=result.raw_response,
    )
    db.add(analysis)
    db.flush()

    for item in result.action_items:
        db.add(MeetingActionItem(
            meeting_id=meeting_id,
            analysis_id=analysis.id,
            description=item.description,
            assignee_name_raw=item.assignee_name_raw,   # NOT resolved to a person
            assignment_method="unassigned",
            priority=item.priority,
            status="pending",
            review_status="proposed",
            is_legacy_conversion=False,
            source="ai",
            ai_confidence=item.confidence,
        ))

    db.commit()
    db.refresh(analysis)
    return analysis


def extract_meeting_audio(
    db: Session,
    meeting_id: int,
    *,
    storage: MeetingVideoStorage | None = None,
) -> Meeting:
    """
    Extract audio from a meeting's stored video and record `audio_path`
    (relative reference only — no bytes in the DB). The source video is
    preserved. Pipeline status transitions are handled by pipeline.py
    (Phase 8), not here.

    Raises HTTP 422 if the meeting has no source video, the video file is
    missing from storage, or FFmpeg fails. No partial audio file is left on
    failure.
    """
    storage = storage or get_storage()
    meeting = get_meeting(db, meeting_id)

    if not meeting.source_video_path:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Meeting has no source video to extract audio from.")

    try:
        source = storage.resolve(meeting.source_video_path)
    except StorageError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if not source.is_file():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Source video file is missing from storage.")

    target = storage.derived_target(meeting_id, meeting_settings.audio_filename)
    try:
        info = extract_audio(
            source, target,
            sample_rate=meeting_settings.audio_sample_rate,
            channels=meeting_settings.audio_channels,
        )
    except AudioExtractionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Audio extraction failed: {exc}")

    meeting.audio_path = storage.to_relative(info.path)
    if info.duration_sec:
        meeting.duration_sec = info.duration_sec
    db.commit()
    db.refresh(meeting)
    return meeting


def delete_meeting(
    db: Session,
    meeting_id: int,
    *,
    storage: MeetingVideoStorage | None = None,
) -> None:
    """Delete a meeting row (children cascade) and its stored files."""
    storage = storage or get_storage()
    meeting = get_meeting(db, meeting_id)
    db.delete(meeting)
    db.commit()
    storage.delete_meeting_files(meeting_id)
