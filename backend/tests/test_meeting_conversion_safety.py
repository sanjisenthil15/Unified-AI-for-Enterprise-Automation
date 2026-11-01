"""Phase 5.2 — meeting action-item conversion safety under real concurrency
and mid-transaction failure (complements test_meeting_action_approval.py,
which covers the sequential lifecycle)."""
import threading

from models.meeting import Meeting
from models.meeting_action_item import MeetingActionItem
from models.sprint_task import SprintTask
from tests.test_meeting_action_approval import EMP_BASE, MEETINGS_BASE, SPR_BASE, _onboard_user, _tag


def _confirmed_item(client, db, new_user, unique_email, tag):
    admin = new_user("Admin User")
    project = client.post(f"{EMP_BASE}/projects", headers=admin["headers"],
                          json={"name": f"P {tag} {unique_email}", "status": "active"}).json()
    mgr = _onboard_user(client, admin["headers"], _tag(unique_email, f"mgr{tag}"), "manager", "Safety Manager")
    member = _onboard_user(client, admin["headers"], _tag(unique_email, f"mem{tag}"), "employee", "Safety Member",
                           project_id=project["id"])
    client.post(f"{EMP_BASE}/projects/{project['id']}/manager", headers=admin["headers"],
                json={"manager_user_id": mgr["user_id"]})
    sprint = client.post(SPR_BASE, headers=mgr["headers"], json={
        "project_id": project["id"], "name": f"Sprint {tag}", "start_date": "2026-02-01", "end_date": "2026-02-07",
    }).json()
    meeting = Meeting(created_by=mgr["user_id"], title="Safety Meeting", project_id=project["id"], status="completed")
    db.add(meeting)
    db.flush()
    item = MeetingActionItem(meeting_id=meeting.id, description="Ship the release notes", assignment_method="unassigned",
                             status="pending", review_status="proposed", source="ai")
    db.add(item)
    db.commit()
    r = client.post(f"{MEETINGS_BASE}/{meeting.id}/action-items/{item.id}/confirm", headers=mgr["headers"],
                    json={"assignee_id": member["employee_id"], "due_date": "2026-02-05"})
    assert r.status_code == 200, r.text
    return {"mgr": mgr, "meeting_id": meeting.id, "item_id": item.id, "sprint_id": sprint["id"]}


def _tasks_in_sprint(db, sprint_id):
    db.expire_all()
    return db.query(SprintTask).filter(SprintTask.sprint_id == sprint_id).count()


def test_concurrent_conversions_create_exactly_one_task(client, db, new_user, unique_email):
    ctx = _confirmed_item(client, db, new_user, unique_email, "cc")
    url = f"{MEETINGS_BASE}/{ctx['meeting_id']}/action-items/{ctx['item_id']}/convert"
    barrier = threading.Barrier(6)
    codes, lock = [], threading.Lock()

    def convert():
        barrier.wait()
        r = client.post(url, headers=ctx["mgr"]["headers"], json={"sprint_id": ctx["sprint_id"]})
        with lock:
            codes.append(r.status_code)

    threads = [threading.Thread(target=convert) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)

    assert sorted(codes) == [200, 409, 409, 409, 409, 409], codes
    assert _tasks_in_sprint(db, ctx["sprint_id"]) == 1
    db.expire_all()
    item = db.get(MeetingActionItem, ctx["item_id"])
    assert item.review_status == "converted" and item.converted_sprint_task_id is not None


def test_failed_conversion_rolls_back_completely(client, db, new_user, unique_email, monkeypatch):
    ctx = _confirmed_item(client, db, new_user, unique_email, "rb")
    from modules.sprints import service as sprints_service

    real_create = sprints_service._create_task_without_commit

    def create_then_fail(*args, **kwargs):
        real_create(*args, **kwargs)  # the task row is flushed...
        raise RuntimeError("simulated failure after task insert")  # ...then the transaction dies

    monkeypatch.setattr(sprints_service, "_create_task_without_commit", create_then_fail)
    url = f"{MEETINGS_BASE}/{ctx['meeting_id']}/action-items/{ctx['item_id']}/convert"
    try:
        client.post(url, headers=ctx["mgr"]["headers"], json={"sprint_id": ctx["sprint_id"]})
    except RuntimeError:
        pass  # TestClient re-raises unhandled server errors
    monkeypatch.undo()

    assert _tasks_in_sprint(db, ctx["sprint_id"]) == 0
    db.expire_all()
    item = db.get(MeetingActionItem, ctx["item_id"])
    assert item.review_status == "confirmed" and item.converted_sprint_task_id is None

    # And a normal retry still works afterwards.
    r = client.post(url, headers=ctx["mgr"]["headers"], json={"sprint_id": ctx["sprint_id"]})
    assert r.status_code == 200, r.text
    assert _tasks_in_sprint(db, ctx["sprint_id"]) == 1
