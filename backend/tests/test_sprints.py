"""Sprints module — sprints, tasks, manager review, and access control."""

EMP_BASE = "/api/v1/employee-management"
SPR_BASE = "/api/v1/sprints"


def _role_id(client, headers, name):
    roles = client.get("/api/v1/auth/roles", headers=headers).json()
    return next(r["id"] for r in roles if r["name"] == name)


def _tag(unique_email, tag):
    """A distinct variant of unique_email for a second onboarded account in
    the same test — keeps "pytest_" as the leading token (conftest's
    cleanup matches emails starting with it), just tagged right after."""
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
    login = client.post("/api/v1/auth/login", json={"email": email, "password": temp_password})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return {"employee_id": employee_id, "headers": headers}


def _make_project_with_lead(client, admin_headers, unique_email):
    project = client.post(f"{EMP_BASE}/projects", headers=admin_headers, json={
        "name": f"Project {unique_email}",
    }).json()
    lead = _onboard(client, admin_headers, _tag(unique_email, "lead"), "Team Lead", project_id=project["id"])
    client.post(f"{EMP_BASE}/projects/{project['id']}/team-lead", headers=admin_headers,
                json={"employee_id": lead["employee_id"]})
    return project, lead


def test_only_manager_can_create_sprint(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    member = _onboard(client, admin["headers"], _tag(unique_email, "member"), "Member", project_id=project["id"])

    # A plain member cannot create a sprint.
    r = client.post(SPR_BASE, headers=member["headers"], json={
        "project_id": project["id"], "name": "Sprint 1", "start_date": "2026-01-05", "end_date": "2026-01-11",
    })
    assert r.status_code == 403

    # The project's team lead can.
    r = client.post(SPR_BASE, headers=lead["headers"], json={
        "project_id": project["id"], "name": "Sprint 1", "start_date": "2026-01-05", "end_date": "2026-01-11",
    })
    assert r.status_code == 201, r.text
    assert r.json()["project"]["id"] == project["id"]

    # Admin (role override, no Employee record) can too.
    r = client.post(SPR_BASE, headers=admin["headers"], json={
        "project_id": project["id"], "name": "Sprint 2", "start_date": "2026-01-12", "end_date": "2026-01-18",
    })
    assert r.status_code == 201, r.text


def test_task_assignment_and_self_update_permissions(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    member = _onboard(client, admin["headers"], _tag(unique_email, "member"), "Member", project_id=project["id"])

    sprint = client.post(SPR_BASE, headers=lead["headers"], json={
        "project_id": project["id"], "name": "Sprint 1", "start_date": "2026-01-05", "end_date": "2026-01-11",
    }).json()

    # A plain member cannot create tasks.
    r = client.post(f"{SPR_BASE}/{sprint['id']}/tasks", headers=member["headers"], json={"title": "Do the thing"})
    assert r.status_code == 403

    task = client.post(f"{SPR_BASE}/{sprint['id']}/tasks", headers=lead["headers"], json={
        "title": "Do the thing", "assignee_id": member["employee_id"],
    }).json()
    assert task["assignee"]["id"] == member["employee_id"]

    notifications = client.get("/api/v1/notifications/me", headers=member["headers"]).json()
    assert any(n["type"] == "task_assigned" for n in notifications)

    # The assignee can update status/progress on their own task.
    r = client.patch(f"{SPR_BASE}/tasks/{task['id']}", headers=member["headers"], json={
        "status": "in_progress", "progress_percent": 50,
    })
    assert r.status_code == 200, r.text
    assert r.json()["progress_percent"] == 50

    # But the assignee cannot retitle or reassign — that's manager-only.
    r = client.patch(f"{SPR_BASE}/tasks/{task['id']}", headers=member["headers"], json={"title": "Sneaky rename"})
    assert r.status_code == 403

    # "done" forces progress to 100.
    r = client.patch(f"{SPR_BASE}/tasks/{task['id']}", headers=member["headers"], json={"status": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["progress_percent"] == 100

    # Some other, unrelated employee cannot touch this task at all.
    outsider = _onboard(client, admin["headers"], _tag(unique_email, "outsider"), "Outsider")
    r = client.patch(f"{SPR_BASE}/tasks/{task['id']}", headers=outsider["headers"], json={"progress_percent": 10})
    assert r.status_code == 403


def test_manager_review_flags_overdue_tasks(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    member = _onboard(client, admin["headers"], _tag(unique_email, "member"), "Member", project_id=project["id"])

    sprint = client.post(SPR_BASE, headers=lead["headers"], json={
        "project_id": project["id"], "name": "Sprint 1", "start_date": "2020-01-01", "end_date": "2020-01-07",
    }).json()

    # Two tasks, both overdue (due_date in the past) and still incomplete ->
    # should trip the "2+ overdue incomplete tasks" flagging rule.
    for i in range(2):
        client.post(f"{SPR_BASE}/{sprint['id']}/tasks", headers=lead["headers"], json={
            "title": f"Overdue task {i}", "assignee_id": member["employee_id"], "due_date": "2020-01-10",
        })

    # A plain member cannot view the review.
    r = client.get(f"{SPR_BASE}/review", headers=member["headers"], params={"project_id": project["id"]})
    assert r.status_code == 403

    r = client.get(f"{SPR_BASE}/review", headers=lead["headers"], params={"project_id": project["id"]})
    assert r.status_code == 200, r.text
    entry = next(e for e in r.json() if e["employee"]["id"] == member["employee_id"])
    assert entry["tasks_overdue_incomplete"] == 2
    assert entry["flagged"] is True


def test_overdue_task_notifies_team_lead_once(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    member = _onboard(client, admin["headers"], _tag(unique_email, "member"), "Member", project_id=project["id"])

    sprint = client.post(SPR_BASE, headers=lead["headers"], json={
        "project_id": project["id"], "name": "Sprint 1", "start_date": "2020-01-01", "end_date": "2020-01-07",
    }).json()
    client.post(f"{SPR_BASE}/{sprint['id']}/tasks", headers=lead["headers"], json={
        "title": "Overdue task", "assignee_id": member["employee_id"], "due_date": "2020-01-10",
    })

    client.get(f"{SPR_BASE}/review", headers=lead["headers"], params={"project_id": project["id"]})
    client.get(f"{SPR_BASE}/review", headers=lead["headers"], params={"project_id": project["id"]})

    notifications = client.get("/api/v1/notifications/me", headers=lead["headers"]).json()
    overdue_notifications = [n for n in notifications if n["type"] == "task_overdue"]
    assert len(overdue_notifications) == 1


def test_generate_weekly_sprints_fills_to_deadline_idempotently(client, new_user, unique_email):
    admin = new_user("Admin User")
    project = client.post(f"{EMP_BASE}/projects", headers=admin["headers"], json={
        "name": f"Project {unique_email}", "deadline": "2027-01-15",
    }).json()
    role_id = _role_id(client, admin["headers"], "employee")
    lead_email = _tag(unique_email, "lead")
    r = client.post(f"{EMP_BASE}/employees", headers=admin["headers"], json={
        "full_name": "Team Lead", "email": lead_email, "role_id": role_id,
        "job_title": "Lead", "project_id": project["id"], "hire_date": "2026-01-01",
    })
    lead_employee_id = r.json()["employee"]["id"]
    client.post(f"{EMP_BASE}/projects/{project['id']}/team-lead", headers=admin["headers"],
                json={"employee_id": lead_employee_id})
    temp_password = r.json()["temporary_password"]
    login = client.post("/api/v1/auth/login", json={"email": lead_email, "password": temp_password})
    lead_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # A plain employee cannot generate sprints.
    outsider = _onboard(client, admin["headers"], _tag(unique_email, "outsider"), "Outsider")
    r = client.post(f"{SPR_BASE}/generate-weekly", headers=outsider["headers"], json={"project_id": project["id"]})
    assert r.status_code == 403

    r = client.post(f"{SPR_BASE}/generate-weekly", headers=lead_headers, json={"project_id": project["id"]})
    assert r.status_code == 200, r.text
    first_batch = r.json()
    assert len(first_batch) > 0
    assert first_batch[-1]["end_date"] == "2027-01-15"

    # Re-running fills nothing further — the deadline is already covered.
    r = client.post(f"{SPR_BASE}/generate-weekly", headers=lead_headers, json={"project_id": project["id"]})
    assert r.status_code == 200, r.text
    assert r.json() == []

    all_sprints = client.get(SPR_BASE, headers=lead_headers, params={"project_id": project["id"]}).json()
    assert len(all_sprints) == len(first_batch)


def test_enterprise_overview_is_admin_only(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)

    r = client.get(f"{SPR_BASE}/overview", headers=lead["headers"])
    assert r.status_code == 403

    r = client.get(f"{SPR_BASE}/overview", headers=admin["headers"])
    assert r.status_code == 200, r.text
    entry = next(e for e in r.json() if e["project_id"] == project["id"])
    assert entry["team_lead"]["id"] == lead["employee_id"]
