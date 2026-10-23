"""Manager Chat module — scoped to the team-lead relationship (or admin/hr_manager)."""

EMP_BASE = "/api/v1/employee-management"
CHAT_BASE = "/api/v1/chat"


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
    user_id = r.json()["employee"]["user"]["id"]
    login = client.post("/api/v1/auth/login", json={"email": email, "password": temp_password})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    return {"employee_id": employee_id, "user_id": user_id, "headers": headers}


def _make_project_with_lead(client, admin_headers, unique_email, tag=""):
    project_email = _tag(unique_email, f"proj{tag}") if tag else unique_email
    project = client.post(f"{EMP_BASE}/projects", headers=admin_headers, json={
        "name": f"Project {project_email}",
    }).json()
    lead = _onboard(client, admin_headers, _tag(unique_email, f"lead{tag}"), "Team Lead", project_id=project["id"])
    client.post(f"{EMP_BASE}/projects/{project['id']}/team-lead", headers=admin_headers,
                json={"employee_id": lead["employee_id"]})
    return project, lead


def test_team_lead_and_member_can_message_each_other(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    member = _onboard(client, admin["headers"], _tag(unique_email, "member"), "Member", project_id=project["id"])

    r = client.post(f"{CHAT_BASE}/threads", headers=lead["headers"], json={"other_user_id": member["user_id"]})
    assert r.status_code == 200, r.text
    thread_id = r.json()["id"]

    r = client.post(f"{CHAT_BASE}/threads/{thread_id}/messages", headers=lead["headers"], json={
        "body": "How's the sprint going?",
    })
    assert r.status_code == 201, r.text

    # The member sees it when they poll the same thread.
    r = client.get(f"{CHAT_BASE}/threads/{thread_id}/messages", headers=member["headers"])
    assert r.status_code == 200, r.text
    assert any(m["body"] == "How's the sprint going?" for m in r.json())

    r = client.post(f"{CHAT_BASE}/threads/{thread_id}/messages", headers=member["headers"], json={
        "body": "Going well!",
    })
    assert r.status_code == 201, r.text

    # since_id lets the lead pull only the new message.
    first_msg_id = client.get(f"{CHAT_BASE}/threads/{thread_id}/messages", headers=lead["headers"]).json()[0]["id"]
    r = client.get(f"{CHAT_BASE}/threads/{thread_id}/messages", headers=lead["headers"], params={"since_id": first_msg_id})
    assert r.status_code == 200, r.text
    assert all(m["body"] != "How's the sprint going?" for m in r.json())


def test_unrelated_employees_cannot_message_each_other(client, new_user, unique_email):
    admin = new_user("Admin User")
    project_a, lead_a = _make_project_with_lead(client, admin["headers"], unique_email, tag="a")
    project_b, lead_b = _make_project_with_lead(client, admin["headers"], unique_email, tag="b")

    r = client.post(f"{CHAT_BASE}/threads", headers=lead_a["headers"], json={"other_user_id": lead_b["user_id"]})
    assert r.status_code == 403


def test_admin_can_message_anyone(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)

    r = client.post(f"{CHAT_BASE}/threads", headers=admin["headers"], json={"other_user_id": lead["user_id"]})
    assert r.status_code == 200, r.text


def test_sending_a_message_creates_a_notification(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    member = _onboard(client, admin["headers"], _tag(unique_email, "member"), "Member", project_id=project["id"])

    thread = client.post(f"{CHAT_BASE}/threads", headers=lead["headers"], json={"other_user_id": member["user_id"]}).json()
    client.post(f"{CHAT_BASE}/threads/{thread['id']}/messages", headers=lead["headers"], json={"body": "Ping"})

    r = client.get("/api/v1/notifications/me", headers=member["headers"])
    assert r.status_code == 200, r.text
    assert any(n["type"] == "chat_message" for n in r.json())
