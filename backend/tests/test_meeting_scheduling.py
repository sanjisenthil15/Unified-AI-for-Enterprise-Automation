"""Meeting scheduling, and an ended Online Meeting being persisted into the
offline Meeting Intelligence history (models.Meeting) instead of being
discarded after the in-memory 24h retention window."""

from datetime import datetime, timedelta, timezone

from models.meeting import Meeting
from models.meeting_action_item import MeetingActionItem
from modules.meeting_intelligence.service import create_or_update_meeting_from_online_session
from modules.meeting_online.schemas import (
    ActionItemResult,
    LiveAnalysisResult,
    OnlineMeetingSession,
    Participant,
    TranscriptSegment,
)

EMP_BASE = "/api/v1/employee-management"
MEETINGS_BASE = "/api/v1/meetings"


def _role_id(client, headers, name):
    roles = client.get("/api/v1/auth/roles", headers=headers).json()
    return next(r["id"] for r in roles if r["name"] == name)


def _tag(unique_email, tag):
    return unique_email.replace("pytest_", f"pytest_{tag}_", 1)


def _onboard(client, admin_headers, email, full_name="Test Employee", project_id=None):
    role_id = _role_id(client, admin_headers, "employee")
    r = client.post(f"{EMP_BASE}/employees", headers=admin_headers, json={
        "full_name": full_name, "email": email, "role_id": role_id,
        "job_title": "Engineer", "project_id": project_id, "hire_date": "2026-01-01",
    })
    assert r.status_code == 201, r.text
    temp_password = r.json()["temporary_password"]
    employee_id = r.json()["employee"]["id"]
    user_id = r.json()["employee"]["user"]["id"]
    login = client.post("/api/v1/auth/login", json={"email": email, "password": temp_password})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return {"employee_id": employee_id, "user_id": user_id, "headers": headers}


def _make_project_with_lead(client, admin_headers, unique_email):
    project = client.post(f"{EMP_BASE}/projects", headers=admin_headers, json={
        "name": f"Project {unique_email}",
    }).json()
    lead = _onboard(client, admin_headers, _tag(unique_email, "lead"), "Team Lead", project_id=project["id"])
    client.post(f"{EMP_BASE}/projects/{project['id']}/team-lead", headers=admin_headers,
                json={"employee_id": lead["employee_id"]})
    return project, lead


def test_schedule_meeting_invites_and_notifies_project_members(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    member = _onboard(client, admin["headers"], _tag(unique_email, "member"), "Member", project_id=project["id"])
    outsider = _onboard(client, admin["headers"], _tag(unique_email, "outsider"), "Outsider")

    when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    r = client.post(f"{MEETINGS_BASE}/schedule", headers=lead["headers"], json={
        "title": "Sprint planning", "project_id": project["id"], "scheduled_at": when,
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["project_name"] == project["name"]
    assert body["invitee_count"] == 2  # lead + member

    # The member is invited and notified; the lead (organizer) sees it too;
    # an outsider never invited does not.
    member_scheduled = client.get(f"{MEETINGS_BASE}/scheduled", headers=member["headers"]).json()
    assert any(m["id"] == body["id"] for m in member_scheduled)

    lead_scheduled = client.get(f"{MEETINGS_BASE}/scheduled", headers=lead["headers"]).json()
    assert any(m["id"] == body["id"] for m in lead_scheduled)

    outsider_scheduled = client.get(f"{MEETINGS_BASE}/scheduled", headers=outsider["headers"]).json()
    assert not any(m["id"] == body["id"] for m in outsider_scheduled)

    member_notifications = client.get("/api/v1/notifications/me", headers=member["headers"]).json()
    assert any(n["type"] == "meeting" and "Sprint planning" in n["message"] for n in member_notifications)


def test_start_online_meeting_links_a_scheduled_booking(client, db, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    member = _onboard(client, admin["headers"], _tag(unique_email, "member"), "Member", project_id=project["id"])

    when = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    scheduled = client.post(f"{MEETINGS_BASE}/schedule", headers=lead["headers"], json={
        "title": "Weekly sync", "project_id": project["id"], "scheduled_at": when,
    }).json()

    # An invited member (not the organizer) cannot start it.
    r = client.post("/api/v1/meetings/online", headers=member["headers"], json={
        "title": "Weekly sync", "request_id": "11111111-1111-1111-1111-111111111111",
        "meeting_id": scheduled["id"],
    })
    assert r.status_code == 404

    # The organizer can — the live session inherits the booking's project.
    r = client.post("/api/v1/meetings/online", headers=lead["headers"], json={
        "title": "Weekly sync", "request_id": "22222222-2222-2222-2222-222222222222",
        "meeting_id": scheduled["id"],
    })
    assert r.status_code == 201, r.text
    assert r.json()["project_id"] == project["id"]
    assert r.json()["linked_meeting_id"] == scheduled["id"]

    # Once the booking is no longer 'scheduled' (the real flow: the linked
    # online session ends and create_or_update_meeting_from_online_session
    # flips it to 'completed' — simulated directly here to avoid depending
    # on that background task's timing), starting it again is rejected.
    db.query(Meeting).filter(Meeting.id == scheduled["id"]).update({"status": "completed"})
    db.commit()
    r = client.post("/api/v1/meetings/online", headers=lead["headers"], json={
        "title": "Weekly sync", "request_id": "33333333-3333-3333-3333-333333333333",
        "meeting_id": scheduled["id"],
    })
    assert r.status_code == 409


def test_schedule_meeting_requires_project_manager(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    member = _onboard(client, admin["headers"], _tag(unique_email, "member"), "Member", project_id=project["id"])

    when = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    r = client.post(f"{MEETINGS_BASE}/schedule", headers=member["headers"], json={
        "title": "Unauthorized booking", "project_id": project["id"], "scheduled_at": when,
    })
    assert r.status_code == 403


def _fake_session(title, owner_user_id, other_user_id):
    started = datetime.now(timezone.utc) - timedelta(minutes=20)
    return OnlineMeetingSession(
        id="11111111-1111-1111-1111-111111111111",
        title=title,
        status="ended",
        started_at=started,
        ended_at=datetime.now(timezone.utc),
        websocket_path="/api/v1/meetings/online/x/ws",
        participants=[
            Participant(client_id="a", speaker="Organizer", connected=False, user_id=owner_user_id),
            Participant(client_id="b", speaker="Teammate", connected=False, user_id=other_user_id),
        ],
        transcript=[
            TranscriptSegment(id="1", speaker="Organizer", text="Let's finish the login page this week.",
                               start_ms=0, end_ms=3000, source="manual"),
        ],
        analysis=LiveAnalysisResult(
            summary="Discussed the login page deadline.",
            key_points=["Login page due this week"],
            decisions=["Ship login page by Friday"],
            action_items=[ActionItemResult(description="Finish the login page", assignee="Teammate",
                                            priority="high", confidence=0.9)],
            model_provider="gemini", model_name="gemini-flash-lite-latest",
        ),
        analysis_status="ready",
    )


def test_online_session_end_persists_to_meeting_history(client, db, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    member = _onboard(client, admin["headers"], _tag(unique_email, "member"), "Member", project_id=project["id"])

    session = _fake_session("Ad-hoc standup", lead["user_id"], member["user_id"])
    meeting_id = create_or_update_meeting_from_online_session(
        db, owner_id=lead["user_id"], session=session, project_id=project["id"], linked_meeting_id=None,
    )
    db.commit()

    r = client.get(f"{MEETINGS_BASE}/{meeting_id}", headers=lead["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"
    assert r.json()["project_id"] == project["id"]

    transcript = client.get(f"{MEETINGS_BASE}/{meeting_id}/transcript", headers=lead["headers"]).json()
    assert "login page" in transcript["full_text"]

    analysis = client.get(f"{MEETINGS_BASE}/{meeting_id}/analysis", headers=lead["headers"]).json()
    assert analysis["summary"] == "Discussed the login page deadline."

    items = client.get(f"{MEETINGS_BASE}/{meeting_id}/action-items", headers=lead["headers"]).json()
    assert len(items) == 1
    assert items[0]["description"] == "Finish the login page"
    assert items[0]["assignment_method"] == "unassigned"

    db.query(MeetingActionItem).filter(MeetingActionItem.meeting_id == meeting_id).delete()
    db.query(Meeting).filter(Meeting.id == meeting_id).delete()
    db.commit()


def test_online_session_fills_in_its_linked_scheduled_meeting(client, db, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)

    when = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    scheduled = client.post(f"{MEETINGS_BASE}/schedule", headers=lead["headers"], json={
        "title": "Weekly sync", "project_id": project["id"], "scheduled_at": when,
    }).json()

    session = _fake_session("Weekly sync", lead["user_id"], lead["user_id"])
    meeting_id = create_or_update_meeting_from_online_session(
        db, owner_id=lead["user_id"], session=session, project_id=None, linked_meeting_id=scheduled["id"],
    )
    db.commit()

    # Same row, not a new one — it has left the scheduled list entirely.
    assert meeting_id == scheduled["id"]
    still_scheduled = client.get(f"{MEETINGS_BASE}/scheduled", headers=lead["headers"]).json()
    assert not any(m["id"] == scheduled["id"] for m in still_scheduled)

    r = client.get(f"{MEETINGS_BASE}/{meeting_id}", headers=lead["headers"])
    assert r.json()["status"] == "completed"
    assert r.json()["project_id"] == project["id"]

    db.query(MeetingActionItem).filter(MeetingActionItem.meeting_id == meeting_id).delete()
    db.query(Meeting).filter(Meeting.id == meeting_id).delete()
    db.commit()
