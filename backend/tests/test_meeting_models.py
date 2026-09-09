"""
ORM integration tests for the Meeting Intelligence schema (Phase 2).

Exercises the models directly against PostgreSQL: relationships, manual
action-item assignment, unique constraints, and ON DELETE CASCADE.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from config.database import SessionLocal, engine
from models.user import User
from models.employee import Employee
from models.meeting import Meeting
from models.meeting_participant import MeetingParticipant
from models.meeting_speaker import MeetingSpeaker
from models.meeting_transcript import MeetingTranscript
from models.meeting_transcript_segment import MeetingTranscriptSegment
from models.meeting_analysis import MeetingAnalysis
from models.meeting_action_item import MeetingActionItem


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.rollback()
        s.close()


@pytest.fixture
def people(db):
    """A user + linked employee to own/assign meeting data. Cleaned up after."""
    tag = uuid.uuid4().hex[:10]
    user = User(
        role_id=1, full_name="MI Test User",
        email=f"mi_{tag}@example.com", hashed_password="x", is_active=True,
    )
    db.add(user)
    db.flush()
    emp = Employee(
        user_id=user.id, employee_code=f"MI-{tag}", job_title="Tester",
        hire_date=date(2024, 1, 1),
    )
    db.add(emp)
    db.commit()
    yield {"user_id": user.id, "employee_id": emp.id}
    # teardown: remove meetings first (created_by is RESTRICT), then people
    db.query(Meeting).filter(Meeting.created_by == user.id).delete()
    db.commit()
    db.query(Employee).filter(Employee.id == emp.id).delete()
    db.query(User).filter(User.id == user.id).delete()
    db.commit()


def _make_full_meeting(db, people) -> Meeting:
    m = Meeting(
        created_by=people["user_id"],
        title="Q3 Planning",
        source_video_path="/data/uploads/meetings/1/source.mp4",
        source_video_filename="q3.mp4",
    )
    db.add(m)
    db.flush()

    m.participants.append(MeetingParticipant(
        user_id=people["user_id"], employee_id=people["employee_id"],
        display_name="MI Test User", role="organizer",
    ))
    sp1 = MeetingSpeaker(meeting_id=m.id, label="Speaker 1")
    sp2 = MeetingSpeaker(meeting_id=m.id, label="Speaker 2")
    db.add_all([sp1, sp2])
    db.flush()

    m.transcript = MeetingTranscript(full_text="hello ... goodbye", word_count=3)
    db.add(MeetingTranscriptSegment(
        meeting_id=m.id, speaker_id=sp1.id, speaker_label="Speaker 1",
        seq=0, start_ms=0, end_ms=1500, text="hello",
    ))
    analysis = MeetingAnalysis(
        meeting_id=m.id, summary="Planned Q3.",
        key_points=["scope agreed"], decisions=["ship in October"],
        model_provider="gemini",
    )
    db.add(analysis)
    db.flush()
    db.add(MeetingActionItem(
        meeting_id=m.id, analysis_id=analysis.id,
        description="Complete recruitment API",
        assignee_name_raw="Person B", source="ai", ai_confidence=0.4,
    ))
    db.commit()
    return m


def test_create_and_read_relationships(db, people):
    m = _make_full_meeting(db, people)
    db.refresh(m)
    assert m.status == "pending"
    assert len(m.participants) == 1
    assert {s.label for s in m.speakers} == {"Speaker 1", "Speaker 2"}
    assert m.transcript.word_count == 3
    assert m.segments[0].speaker.label == "Speaker 1"
    assert m.analysis.decisions == ["ship in October"]
    assert len(m.analysis.action_items) == 1


def test_action_item_defaults_to_unassigned(db, people):
    m = _make_full_meeting(db, people)
    item = m.action_items[0]
    assert item.status == "pending"
    assert item.assignment_method == "unassigned"
    assert item.assigned_to_user_id is None
    assert item.assignee_name_raw == "Person B"  # AI mention kept, not resolved


def test_manual_assignment(db, people):
    m = _make_full_meeting(db, people)
    item = m.action_items[0]
    item.assigned_to_user_id = people["user_id"]
    item.assigned_to_employee_id = people["employee_id"]
    item.assignment_method = "manual"
    item.due_date = date(2026, 10, 2)
    item.status = "in_progress"
    db.commit()
    db.refresh(item)
    assert item.assigned_user.id == people["user_id"]
    assert item.assignment_method == "manual"


def test_speaker_label_unique_per_meeting(db, people):
    m = _make_full_meeting(db, people)
    db.add(MeetingSpeaker(meeting_id=m.id, label="Speaker 1"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_cascade_delete_removes_children(db, people):
    m = _make_full_meeting(db, people)
    mid = m.id
    db.delete(m)
    db.commit()
    for tbl in ("meeting_participants", "meeting_speakers", "meeting_transcripts",
                "meeting_transcript_segments", "meeting_analyses", "meeting_action_items"):
        n = db.execute(text(f"SELECT count(*) FROM {tbl} WHERE meeting_id = :m"), {"m": mid}).scalar()
        assert n == 0, f"{tbl} still has rows after meeting delete"
