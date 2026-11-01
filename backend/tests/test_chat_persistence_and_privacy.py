"""
test_chat_persistence_and_privacy.py

Comprehensive regression tests for Project Team Chat:
- Private 1:1 chat between team members on the same project.
- Strict privacy: third-party employees and Admin (when not a party) cannot read private threads.
- Authenticated sender identity enforcement (no sender spoofing).
- Database persistence in `manager_chat_messages` and `chat_channel_messages`.
- Project group chat scoping: only project members can access.
- Transferred/removed employees lose access to the old project's group.
- Channel message pagination using `since_id`.
"""

from models.manager_chat_message import ManagerChatMessage
from models.manager_chat_thread import ManagerChatThread
from models.chat_channel_message import ChatChannelMessage
from tests.helpers import complete_first_login

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
    headers = complete_first_login(client, email, temp_password)
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


def test_teammates_on_same_project_can_find_and_message_each_other(client, new_user, unique_email, db):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    alice = _onboard(client, admin["headers"], _tag(unique_email, "alice"), "Alice Engineer", project_id=project["id"])
    bob = _onboard(client, admin["headers"], _tag(unique_email, "bob"), "Bob Engineer", project_id=project["id"])

    # Alice sees Bob in contacts
    contacts = client.get(f"{CHAT_BASE}/contacts", headers=alice["headers"]).json()
    assert any(c["user_id"] == bob["user_id"] for c in contacts)

    # Alice initiates private thread with Bob
    r = client.post(f"{CHAT_BASE}/threads", headers=alice["headers"], json={"other_user_id": bob["user_id"]})
    assert r.status_code == 200, r.text
    thread_id = r.json()["id"]

    # Verify thread in database
    db_thread = db.query(ManagerChatThread).filter(ManagerChatThread.id == thread_id).first()
    assert db_thread is not None

    # Alice sends private message
    msg_body = "Hey Bob, let's coordinate on ticket 402."
    r_msg = client.post(f"{CHAT_BASE}/threads/{thread_id}/messages", headers=alice["headers"], json={"body": msg_body})
    assert r_msg.status_code == 201
    msg_id = r_msg.json()["id"]

    # Verify message in PostgreSQL
    db_msg = db.query(ManagerChatMessage).filter(ManagerChatMessage.id == msg_id).first()
    assert db_msg is not None
    assert db_msg.thread_id == thread_id
    assert db_msg.sender_user_id == alice["user_id"]
    assert db_msg.body == msg_body

    # Bob polls and sees the message
    bob_msgs = client.get(f"{CHAT_BASE}/threads/{thread_id}/messages", headers=bob["headers"]).json()
    assert any(m["id"] == msg_id and m["body"] == msg_body for m in bob_msgs)


def test_private_chat_strictly_private_against_outsider_and_admin(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    alice = _onboard(client, admin["headers"], _tag(unique_email, "p_alice"), "Alice", project_id=project["id"])
    bob = _onboard(client, admin["headers"], _tag(unique_email, "p_bob"), "Bob", project_id=project["id"])
    outsider = _onboard(client, admin["headers"], _tag(unique_email, "p_out"), "Outsider")

    # Alice & Bob thread
    thread = client.post(f"{CHAT_BASE}/threads", headers=alice["headers"], json={"other_user_id": bob["user_id"]}).json()
    thread_id = thread["id"]

    client.post(f"{CHAT_BASE}/threads/{thread_id}/messages", headers=alice["headers"], json={"body": "Confidential peer chat."})

    # Outsider cannot read
    r_out = client.get(f"{CHAT_BASE}/threads/{thread_id}/messages", headers=outsider["headers"])
    assert r_out.status_code == 403

    # Outsider cannot send
    r_out_send = client.post(f"{CHAT_BASE}/threads/{thread_id}/messages", headers=outsider["headers"], json={"body": "intruder"})
    assert r_out_send.status_code == 403

    # Admin (not a participant) cannot read private chat
    r_admin = client.get(f"{CHAT_BASE}/threads/{thread_id}/messages", headers=admin["headers"])
    assert r_admin.status_code == 403


def test_sender_identity_cannot_be_spoofed_in_private_chat(client, new_user, unique_email, db):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    alice = _onboard(client, admin["headers"], _tag(unique_email, "s_alice"), "Alice", project_id=project["id"])
    bob = _onboard(client, admin["headers"], _tag(unique_email, "s_bob"), "Bob", project_id=project["id"])

    thread = client.post(f"{CHAT_BASE}/threads", headers=alice["headers"], json={"other_user_id": bob["user_id"]}).json()

    # Alice sends message
    r = client.post(f"{CHAT_BASE}/threads/{thread['id']}/messages", headers=alice["headers"], json={"body": "Message from Alice"})
    msg_id = r.json()["id"]

    db_msg = db.query(ManagerChatMessage).filter(ManagerChatMessage.id == msg_id).first()
    assert db_msg.sender_user_id == alice["user_id"]
    assert db_msg.sender_user_id != bob["user_id"]


def test_project_group_message_persists_in_database(client, new_user, unique_email, db):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)
    alice = _onboard(client, admin["headers"], _tag(unique_email, "g_alice"), "Alice", project_id=project["id"])

    group = client.post(f"{CHAT_BASE}/groups", headers=lead["headers"], json={
        "project_id": project["id"], "name": "Sprint Chat", "member_user_ids": [alice["user_id"]],
    }).json()

    channels = client.get(f"{CHAT_BASE}/groups/{group['id']}/channels", headers=lead["headers"]).json()
    channel_id = channels[0]["id"]

    body = "Sprint kickoff message for all project members."
    r = client.post(f"{CHAT_BASE}/channels/{channel_id}/messages", headers=alice["headers"], json={"body": body})
    assert r.status_code == 201
    msg_id = r.json()["id"]

    # Verify in PostgreSQL
    db_msg = db.query(ChatChannelMessage).filter(ChatChannelMessage.id == msg_id).first()
    assert db_msg is not None
    assert db_msg.channel_id == channel_id
    assert db_msg.sender_user_id == alice["user_id"]
    assert db_msg.body == body


def test_unrelated_project_member_cannot_access_group(client, new_user, unique_email):
    admin = new_user("Admin User")
    project_a, lead_a = _make_project_with_lead(client, admin["headers"], unique_email, tag="a")
    project_b, lead_b = _make_project_with_lead(client, admin["headers"], unique_email, tag="b")
    bob = _onboard(client, admin["headers"], _tag(unique_email, "bob_b"), "Bob B", project_id=project_b["id"])

    group_a = client.post(f"{CHAT_BASE}/groups", headers=lead_a["headers"], json={
        "project_id": project_a["id"], "name": "Group A",
    }).json()

    channels_a = client.get(f"{CHAT_BASE}/groups/{group_a['id']}/channels", headers=lead_a["headers"]).json()
    ch_id = channels_a[0]["id"]

    # Bob (Project B) cannot access Group A
    r_detail = client.get(f"{CHAT_BASE}/groups/{group_a['id']}", headers=bob["headers"])
    assert r_detail.status_code == 403

    # Bob cannot read messages in Group A channel
    r_msgs = client.get(f"{CHAT_BASE}/channels/{ch_id}/messages", headers=bob["headers"])
    assert r_msgs.status_code == 403

    # Bob cannot send messages in Group A channel
    r_send = client.post(f"{CHAT_BASE}/channels/{ch_id}/messages", headers=bob["headers"], json={"body": "intruder"})
    assert r_send.status_code == 403


def test_transferred_employee_loses_access_to_old_project_group(client, new_user, unique_email):
    admin = new_user("Admin User")
    project_a, lead_a = _make_project_with_lead(client, admin["headers"], unique_email, tag="ta")
    project_b, lead_b = _make_project_with_lead(client, admin["headers"], unique_email, tag="tb")

    # Charlie starts on Project A
    charlie = _onboard(client, admin["headers"], _tag(unique_email, "charlie"), "Charlie", project_id=project_a["id"])

    group_a = client.post(f"{CHAT_BASE}/groups", headers=lead_a["headers"], json={
        "project_id": project_a["id"], "name": "Group TA", "member_user_ids": [charlie["user_id"]],
    }).json()
    channels_a = client.get(f"{CHAT_BASE}/groups/{group_a['id']}/channels", headers=lead_a["headers"]).json()
    ch_a_id = channels_a[0]["id"]

    # Charlie can initially access Group A
    r_init = client.get(f"{CHAT_BASE}/groups/{group_a['id']}", headers=charlie["headers"])
    assert r_init.status_code == 200

    # Admin transfers Charlie to Project B
    r_tr = client.patch(f"{EMP_BASE}/employees/{charlie['employee_id']}", headers=admin["headers"], json={
        "project_id": project_b["id"],
    })
    assert r_tr.status_code == 200

    # Charlie loses access to Group A
    r_after = client.get(f"{CHAT_BASE}/groups/{group_a['id']}", headers=charlie["headers"])
    assert r_after.status_code == 403

    # Charlie cannot send message to Group A channel
    r_send = client.post(f"{CHAT_BASE}/channels/{ch_a_id}/messages", headers=charlie["headers"], json={"body": "still here?"})
    assert r_send.status_code == 403


def test_channel_pagination_using_since_id(client, new_user, unique_email):
    admin = new_user("Admin User")
    project, lead = _make_project_with_lead(client, admin["headers"], unique_email)

    group = client.post(f"{CHAT_BASE}/groups", headers=lead["headers"], json={
        "project_id": project["id"], "name": "Paging Group",
    }).json()
    channels = client.get(f"{CHAT_BASE}/groups/{group['id']}/channels", headers=lead["headers"]).json()
    ch_id = channels[0]["id"]

    m1 = client.post(f"{CHAT_BASE}/channels/{ch_id}/messages", headers=lead["headers"], json={"body": "msg 1"}).json()
    m2 = client.post(f"{CHAT_BASE}/channels/{ch_id}/messages", headers=lead["headers"], json={"body": "msg 2"}).json()
    m3 = client.post(f"{CHAT_BASE}/channels/{ch_id}/messages", headers=lead["headers"], json={"body": "msg 3"}).json()

    # Poll with since_id = m1.id -> only m2 and m3 returned
    paged = client.get(f"{CHAT_BASE}/channels/{ch_id}/messages", headers=lead["headers"], params={"since_id": m1["id"]}).json()
    paged_ids = [m["id"] for m in paged]
    assert m1["id"] not in paged_ids
    assert m2["id"] in paged_ids
    assert m3["id"] in paged_ids

