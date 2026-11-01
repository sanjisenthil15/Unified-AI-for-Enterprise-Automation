import pytest
from starlette.testclient import TestClient
from main import app
from config.database import SessionLocal
from models.user import User
from models.role import Role
from core.security import create_access_token


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def hr_manager_token(db_session):
    hr = db_session.query(User).join(Role).filter(Role.name == "hr_manager", User.deleted_at.is_(None)).first()
    if not hr:
        pytest.skip("Active HR Manager user not found in DB")
    return create_access_token(data={"sub": str(hr.id), "email": hr.email, "role": "hr_manager", "ver": hr.token_version}), hr


@pytest.fixture
def admin_token(db_session):
    admin = db_session.query(User).join(Role).filter(Role.name == "admin", User.deleted_at.is_(None)).first()
    if not admin:
        pytest.skip("Active Admin user not found in DB")
    return create_access_token(data={"sub": str(admin.id), "email": admin.email, "role": "admin", "ver": admin.token_version}), admin


@pytest.fixture
def support_agent(db_session):
    agent = db_session.query(User).join(Role).filter(Role.name == "support_agent", User.deleted_at.is_(None)).first()
    if not agent:
        pytest.skip("Active Support Agent user not found in DB")
    return agent


def test_ticket_customer_identity_derived_from_authenticated_user(hr_manager_token):
    token, hr_user = hr_manager_token
    client = TestClient(app)

    # Attempt to spoof customer_name as 'Enterprise Admin'
    payload = {
        "subject": "HR Manager Leave Request System Issue",
        "description": "Encountering error when approving employee leave requests in portal.",
        "customer_name": "Enterprise Admin",
        "customer_email": "admin@enterprise.ai",
        "priority": "high",
        "channel": "web",
    }

    r = client.post(
        "/api/v1/customer-support/tickets",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201
    data = r.json()

    # Identity MUST be derived from HR user, NOT the spoofed payload!
    assert data["submitted_by"] == hr_user.id
    assert data["customer_name"] == hr_user.full_name
    assert data["customer_email"] == hr_user.email
    assert data["customer_role"] == "hr_manager"
    # Agent must be Unassigned (None)
    assert data["assigned_to"] is None
    assert data["assigned_agent_name"] is None


def test_agent_listing_and_ticket_assignment(admin_token, support_agent):
    token, admin_user = admin_token
    client = TestClient(app)

    # 1. Admin lists eligible agents
    r_agents = client.get(
        "/api/v1/customer-support/agents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_agents.status_code == 200
    agents_list = r_agents.json()
    assert any(a["id"] == support_agent.id for a in agents_list)

    # 2. Create ticket as admin
    payload = {
        "subject": "Platform Infrastructure Maintenance Issue",
        "description": "Database connection pool experiencing elevated latency during peak hours.",
        "priority": "medium",
        "channel": "web",
    }
    r_create = client.post(
        "/api/v1/customer-support/tickets",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_create.status_code == 201
    tkt_id = r_create.json()["id"]

    # 3. Assign ticket to support agent
    r_update = client.put(
        f"/api/v1/customer-support/tickets/{tkt_id}",
        json={"assigned_to": support_agent.id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_update.status_code == 200
    updated_data = r_update.json()
    assert updated_data["assigned_to"] == support_agent.id
    assert updated_data["assigned_agent_name"] == support_agent.full_name
    assert updated_data["agent"]["id"] == support_agent.id
    assert updated_data["status"] == "assigned"

    # 4. Unassign ticket
    r_unassign = client.put(
        f"/api/v1/customer-support/tickets/{tkt_id}",
        json={"assigned_to": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r_unassign.status_code == 200
    assert r_unassign.json()["assigned_to"] is None
    assert r_unassign.json()["assigned_agent_name"] is None
