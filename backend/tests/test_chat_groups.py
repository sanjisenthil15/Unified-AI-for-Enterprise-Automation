"""Chat groups & channels — Discord-style project-scoped group chat."""

EMP_BASE = "/api/v1/employee-management"
CHAT_BASE = "/api/v1/chat"


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


def test_only_manager_can_create_group(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    member = _onboard(client, admin["headers"], _tag(unique_email, "member"), "Member", project_id=project["id"])

    r = client.post(f"{CHAT_BASE}/groups", headers=member["headers"], json={
        "project_id": project["id"], "name": "Team Group", "member_user_ids": [],
    })
    assert r.status_code == 403

    r = client.post(f"{CHAT_BASE}/groups", headers=lead["headers"], json={
        "project_id": project["id"], "name": "Team Group", "member_user_ids": [member["user_id"]],
    })
    assert r.status_code == 201, r.text
    group = r.json()
    assert group["member_count"] == 2  # lead (creator) + member

    # A new group always has a "general" channel.
    channels = client.get(f"{CHAT_BASE}/groups/{group['id']}/channels", headers=lead["headers"]).json()
    assert any(c["name"] == "general" for c in channels)


def test_non_member_cannot_see_group_or_post(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    member = _onboard(client, admin["headers"], _tag(unique_email, "member"), "Member", project_id=project["id"])
    outsider = _onboard(client, admin["headers"], _tag(unique_email, "outsider"), "Outsider")

    group = client.post(f"{CHAT_BASE}/groups", headers=lead["headers"], json={
        "project_id": project["id"], "name": "Team Group", "member_user_ids": [member["user_id"]],
    }).json()

    r = client.get(f"{CHAT_BASE}/groups/{group['id']}", headers=outsider["headers"])
    assert r.status_code == 403

    channels = client.get(f"{CHAT_BASE}/groups/{group['id']}/channels", headers=lead["headers"]).json()
    general_channel_id = next(c["id"] for c in channels if c["name"] == "general")

    r = client.post(f"{CHAT_BASE}/channels/{general_channel_id}/messages", headers=outsider["headers"], json={"body": "hi"})
    assert r.status_code == 403


def test_any_member_can_create_channel_and_post(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    member = _onboard(client, admin["headers"], _tag(unique_email, "member"), "Member", project_id=project["id"])

    group = client.post(f"{CHAT_BASE}/groups", headers=lead["headers"], json={
        "project_id": project["id"], "name": "Team Group", "member_user_ids": [member["user_id"]],
    }).json()

    # The member (not the manager) creates a new channel.
    r = client.post(f"{CHAT_BASE}/groups/{group['id']}/channels", headers=member["headers"], json={"name": "leave"})
    assert r.status_code == 201, r.text
    channel_id = r.json()["id"]

    r = client.post(f"{CHAT_BASE}/channels/{channel_id}/messages", headers=member["headers"], json={"body": "Taking Friday off"})
    assert r.status_code == 201, r.text

    # The lead (also a member) sees it.
    messages = client.get(f"{CHAT_BASE}/channels/{channel_id}/messages", headers=lead["headers"]).json()
    assert any(m["body"] == "Taking Friday off" for m in messages)


def test_duplicate_channel_name_rejected(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    group = client.post(f"{CHAT_BASE}/groups", headers=lead["headers"], json={
        "project_id": project["id"], "name": "Team Group", "member_user_ids": [],
    }).json()

    r = client.post(f"{CHAT_BASE}/groups/{group['id']}/channels", headers=lead["headers"], json={"name": "general"})
    assert r.status_code == 409


def test_admin_sees_and_can_post_in_groups_without_being_a_member(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    member = _onboard(client, admin["headers"], _tag(unique_email, "member"), "Member", project_id=project["id"])

    group = client.post(f"{CHAT_BASE}/groups", headers=lead["headers"], json={
        "project_id": project["id"], "name": "Team Group", "member_user_ids": [member["user_id"]],
    }).json()

    # Admin never joined this group, but the standing override (same as
    # attendance/sprints/review) means they can still see and use it.
    groups = client.get(f"{CHAT_BASE}/groups", headers=admin["headers"]).json()
    assert any(g["id"] == group["id"] for g in groups)

    r = client.get(f"{CHAT_BASE}/groups/{group['id']}", headers=admin["headers"])
    assert r.status_code == 200, r.text
    general_channel_id = next(c["id"] for c in r.json()["channels"] if c["name"] == "general")

    r = client.post(f"{CHAT_BASE}/channels/{general_channel_id}/messages", headers=admin["headers"], json={"body": "Checking in on the team."})
    assert r.status_code == 201, r.text

    messages = client.get(f"{CHAT_BASE}/channels/{general_channel_id}/messages", headers=lead["headers"]).json()
    assert any(m["body"] == "Checking in on the team." for m in messages)


def test_delete_channel_requires_manager_and_keeps_at_least_one(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    member = _onboard(client, admin["headers"], _tag(unique_email, "member"), "Member", project_id=project["id"])

    group = client.post(f"{CHAT_BASE}/groups", headers=lead["headers"], json={
        "project_id": project["id"], "name": "Team Group", "member_user_ids": [member["user_id"]],
    }).json()
    channel = client.post(f"{CHAT_BASE}/groups/{group['id']}/channels", headers=lead["headers"], json={"name": "leave"}).json()

    # A plain member cannot delete a channel.
    r = client.delete(f"{CHAT_BASE}/channels/{channel['id']}", headers=member["headers"])
    assert r.status_code == 403

    # The lead can delete the extra channel.
    r = client.delete(f"{CHAT_BASE}/channels/{channel['id']}", headers=lead["headers"])
    assert r.status_code == 204

    # But not the last remaining one ("general").
    channels = client.get(f"{CHAT_BASE}/groups/{group['id']}/channels", headers=lead["headers"]).json()
    assert len(channels) == 1
    r = client.delete(f"{CHAT_BASE}/channels/{channels[0]['id']}", headers=lead["headers"])
    assert r.status_code == 400


def test_delete_group_requires_manager_and_removes_everything(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    member = _onboard(client, admin["headers"], _tag(unique_email, "member"), "Member", project_id=project["id"])

    group = client.post(f"{CHAT_BASE}/groups", headers=lead["headers"], json={
        "project_id": project["id"], "name": "Team Group", "member_user_ids": [member["user_id"]],
    }).json()

    r = client.delete(f"{CHAT_BASE}/groups/{group['id']}", headers=member["headers"])
    assert r.status_code == 403

    r = client.delete(f"{CHAT_BASE}/groups/{group['id']}", headers=lead["headers"])
    assert r.status_code == 204

    groups = client.get(f"{CHAT_BASE}/groups", headers=lead["headers"]).json()
    assert not any(g["id"] == group["id"] for g in groups)
