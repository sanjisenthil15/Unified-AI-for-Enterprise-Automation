"""Customer Support must never present the in-memory demo store's seeded
sample tickets (#1001–#1003) as real records.

Part 1 runs the service against a genuinely empty, isolated SQLite
database (the shared dev Postgres always has tickets in it). Part 2 uses
the real API on Postgres to prove persisted tickets, privacy and RBAC
still behave as before."""
import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import BigInteger, SmallInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from modules.customer_support import service as cs
from modules.customer_support.schemas import TicketMessageRequest, TicketUpdateRequest


# SQLite only autoincrements an "INTEGER" primary key (same shim as
# test_customer_support_phase3.py).
@compiles(BigInteger, "sqlite")
def _bigint_sqlite(type_, compiler, **kw):
    return "INTEGER"


@compiles(SmallInteger, "sqlite")
def _smallint_sqlite(type_, compiler, **kw):
    return "INTEGER"


SAMPLES = cs.DevFallbackStore().tickets  # a fresh store: seeded samples only
SAMPLE_IDS = [t["id"] for t in SAMPLES]
SAMPLE_SUBJECTS = {t["subject"] for t in SAMPLES}


def _user(role, uid=7, email="someone@example.com"):
    return SimpleNamespace(id=uid, email=email, role=SimpleNamespace(name=role))


@pytest.fixture
def empty_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_seeded_samples_still_exist_in_demo_store():
    """Guards the tests below: they must be checking against real samples."""
    assert len(SAMPLE_IDS) >= 3 and {1001, 1002, 1003} <= set(SAMPLE_IDS)


# ------------------------------------------------------------ empty database

@pytest.mark.parametrize("role", ["admin", "support_agent", "employee"])
def test_empty_database_returns_empty_ticket_list(empty_db, role):
    assert cs.list_support_tickets(empty_db, current_user=_user(role, uid=1)) == []


@pytest.mark.parametrize("status_filter", ["escalated", "open", "resolved", "ALL"])
def test_status_filters_never_return_seeded_tickets(empty_db, status_filter):
    rows = cs.list_support_tickets(empty_db, current_user=_user("admin", uid=1), status_filter=status_filter)
    assert rows == []


def test_empty_database_statistics_are_zero(empty_db):
    stats = cs.get_customer_support_stats(empty_db)
    assert stats.total_tickets == 0
    assert stats.open_tickets == 0
    assert stats.escalated_tickets == 0
    assert stats.resolved_tickets == 0
    assert stats.active_sessions == 0
    assert stats.ai_resolved_sessions == 0  # previously forced to at least 1


@pytest.mark.parametrize("ticket_id", [1001, 1002, 1003])
def test_seeded_ticket_ids_cannot_be_retrieved_or_modified(empty_db, ticket_id):
    admin = _user("admin", uid=1)
    for call in (
        lambda: cs.get_support_ticket(empty_db, ticket_id, current_user=admin),
        lambda: cs.update_support_ticket(empty_db, ticket_id, TicketUpdateRequest(status="resolved"), current_user=admin),
        lambda: cs.add_ticket_message(empty_db, ticket_id, TicketMessageRequest(message="hello"), sender_id=1, current_user=admin),
    ):
        with pytest.raises(HTTPException) as exc:
            call()
        assert exc.value.status_code == 404


def test_global_search_returns_no_seeded_tickets(empty_db):
    for subject in SAMPLE_SUBJECTS:
        term = subject.split()[0]
        result = cs.global_customer_support_search(empty_db, query=term, current_user=_user("admin", uid=1))
        assert not [r for r in result.results if r.type == "ticket"], subject


# ------------------------------------------------------------ real database via the API

def _new_ticket(client, headers, subject):
    categories = client.get("/api/v1/customer-support/categories", headers=headers).json()
    r = client.post("/api/v1/customer-support/tickets", headers=headers, json={
        "subject": subject, "description": "Regression check for real persisted tickets.",
        "priority": "medium", "category_id": categories[0]["id"] if categories else None, "channel": "web",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_real_tickets_privacy_and_rbac_unchanged(client, new_user):
    owner = new_user("Ticket Owner", role="employee")
    other = new_user("Other Employee", role="employee")
    agent = new_user("Support Agent", role="support_agent")
    subject = f"Real ticket {uuid.uuid4().hex[:8]}"
    ticket_id = _new_ticket(client, owner["headers"], subject)
    base = "/api/v1/customer-support/tickets"

    # The owner sees and opens their real, persisted ticket.
    mine = client.get(base, headers=owner["headers"]).json()
    assert [t["id"] for t in mine] == [ticket_id]
    assert client.get(f"{base}/{ticket_id}", headers=owner["headers"]).json()["subject"] == subject

    # Another employee: no list entry, no detail, no reply, no search hit — and
    # no seeded samples either (their own list is legitimately empty).
    assert client.get(base, headers=other["headers"]).json() == []
    assert client.get(f"{base}/{ticket_id}", headers=other["headers"]).status_code == 403
    assert client.post(f"{base}/{ticket_id}/messages", headers=other["headers"],
                       json={"message": "intruding"}).status_code == 403
    found = client.get("/api/v1/customer-support/global-search", headers=other["headers"],
                       params={"q": subject}).json()["results"]
    assert not [r for r in found if r["type"] == "ticket"]

    # Support agent: full access, and only real tickets.
    all_tickets = client.get(base, headers=agent["headers"], params={"limit": 100}).json()
    assert ticket_id in [t["id"] for t in all_tickets]
    assert not SAMPLE_SUBJECTS & {t["subject"] for t in all_tickets}
    escalated = client.get(base, headers=agent["headers"], params={"status": "escalated", "limit": 100}).json()
    assert not SAMPLE_SUBJECTS & {t["subject"] for t in escalated}
    assert client.put(f"{base}/{ticket_id}", headers=agent["headers"], json={"status": "in_progress"}).status_code == 200
    assert client.get(f"{base}/{ticket_id}", headers=owner["headers"]).json()["status"] == "in_progress"

    # Employees still can't change ticket status.
    assert client.put(f"{base}/{ticket_id}", headers=owner["headers"], json={"status": "closed"}).status_code == 403

    # Seeded sample IDs are not real tickets, even for full-access roles.
    for sample_id in SAMPLE_IDS:
        r = client.get(f"{base}/{sample_id}", headers=agent["headers"])
        assert r.status_code == 404 or r.json()["subject"] not in SAMPLE_SUBJECTS


def test_stats_count_only_real_tickets(client, new_user):
    agent = new_user("Stats Agent", role="support_agent")
    before = client.get("/api/v1/customer-support/stats", headers=agent["headers"]).json()["total_tickets"]
    owner = new_user("Stats Owner", role="employee")
    _new_ticket(client, owner["headers"], f"Stats ticket {uuid.uuid4().hex[:8]}")
    after = client.get("/api/v1/customer-support/stats", headers=agent["headers"]).json()["total_tickets"]
    assert after == before + 1
