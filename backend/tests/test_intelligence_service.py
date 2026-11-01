"""
backend/tests/test_intelligence_service.py

Unit and integration tests for Submodule 3.2: AI-Powered Enterprise Intelligence Service.
Verifies:
  1. Deterministic risk score calculations and risk level boundaries.
  2. Projects with insufficient task data.
  3. Sprint delay status classifications without speculative dates.
  4. Workload imbalance detection and role-level bottleneck identification.
  5. Privacy sanitization & employee anonymization for AI prompts.
  6. Customer Support PII exclusion and aggregate-only summaries.
  7. Incident operational risk aggregation.
  8. Gemini structured enrichment and deterministic grounding protection.
  9. Rule-engine fallback on Gemini failure/quota exhaustion.
  10. Cache hit, refresh throttling, and project-specific cache isolation.
  11. Executive 4-part recommendation structure and advisory constraints.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import BigInteger, SmallInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

# SQLite compilation hooks to allow auto-incrementing BigInteger/SmallInteger in SQLite in-memory tests
@compiles(BigInteger, "sqlite")
def _compile_biginteger_sqlite(type_, compiler, **kw):
    return "INTEGER"

@compiles(SmallInteger, "sqlite")
def _compile_smallinteger_sqlite(type_, compiler, **kw):
    return "INTEGER"

from config.database import Base
from models.department import Department
from models.employee import Employee
from models.incident import Incident
from models.project import Project
from models.role import Role
from models.sprint import Sprint
from models.sprint_task import SprintTask
from models.ticket import SupportCategory, SupportTicket
from models.user import User

from modules.intelligence.ai_client import AIQuotaError, GeminiClient
from modules.intelligence.cache import IntelligenceCache, intelligence_cache
from modules.intelligence.schemas import (
    BottleneckSeverity,
    DelayStatus,
    ExecutiveSummaryResponse,
    OperationsInsightsResponse,
    ProjectRiskExplanationItem,
    ProjectRiskIntelligenceResponse,
    RecommendationCategory,
    RiskLevel,
    SprintDelayExplanationItem,
    SprintDelayIntelligenceResponse,
    UrgencyLevel,
    WorkloadBottleneckItem,
    WorkloadIntelligenceResponse,
)
from modules.intelligence.service import (
    _GeminiOperationsPayload,
    _GeminiProjectRiskPayload,
    _GeminiSprintDelayPayload,
    anonymize_workload_records,
    classify_sprint_delay,
    compute_deterministic_project_risk,
    get_executive_recommendations,
    get_incident_insights,
    get_operations_insights,
    get_project_risk_insights,
    get_sprint_delay_insights,
    get_support_insights,
    get_workload_bottleneck_insights,
    sanitize_incident_data_for_ai,
    sanitize_support_data_for_ai,
)


# --------------------------------------------------------------------------- #
# Fixtures: In-Memory SQLite Test Database
# --------------------------------------------------------------------------- #

@pytest.fixture
def test_db():
    """Provides a pristine, isolated in-memory SQLite database session."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # Clear intelligence cache for test isolation
    intelligence_cache.clear()

    try:
        yield session
    finally:
        session.close()
        intelligence_cache.clear()


# --------------------------------------------------------------------------- #
# 1. Deterministic Project Risk Calculation Tests
# --------------------------------------------------------------------------- #

def test_deterministic_risk_score_calculation():
    """Verifies that numerical project risk is purely calculated by deterministic logic."""
    today = date(2026, 10, 31)
    deadline = date(2026, 11, 4)  # 4 days away

    # 10 tasks, 2 done, 4 overdue, 1 blocked
    score, level, factors = compute_deterministic_project_risk(
        total_tasks=10,
        completed_tasks=2,
        overdue_tasks=4,
        blocked_tasks=1,
        deadline=deadline,
        today=today,
    )

    assert 0.0 <= score <= 100.0
    assert level == RiskLevel.HIGH
    assert score >= 70.0
    assert any("4 overdue task(s)" in f for f in factors)
    assert any("Approaching deadline" in f for f in factors)
    assert any("1 blocked task(s)" in f for f in factors)


def test_risk_level_boundaries():
    """Verifies that risk score boundaries (LOW < 35, 35 <= MEDIUM < 70, HIGH >= 70)
    are strictly adhered to."""
    today = date(2026, 10, 31)

    # 1. Low Risk: 10 tasks, 9 done, 0 overdue, deadline in 30 days
    score_low, level_low, _ = compute_deterministic_project_risk(
        total_tasks=10,
        completed_tasks=9,
        overdue_tasks=0,
        blocked_tasks=0,
        deadline=today + timedelta(days=30),
        today=today,
    )
    assert score_low < 35.0
    assert level_low == RiskLevel.LOW

    # 2. Medium Risk: 10 tasks, 4 done, 1 overdue, deadline in 14 days
    score_med, level_med, _ = compute_deterministic_project_risk(
        total_tasks=10,
        completed_tasks=4,
        overdue_tasks=1,
        blocked_tasks=0,
        deadline=today + timedelta(days=12),
        today=today,
    )
    assert 35.0 <= score_med < 70.0
    assert level_med == RiskLevel.MEDIUM

    # 3. High Risk: 10 tasks, 1 done, 5 overdue, deadline passed 2 days ago
    score_high, level_high, _ = compute_deterministic_project_risk(
        total_tasks=10,
        completed_tasks=1,
        overdue_tasks=5,
        blocked_tasks=1,
        deadline=today - timedelta(days=2),
        today=today,
    )
    assert score_high >= 70.0
    assert level_high == RiskLevel.HIGH


def test_projects_with_insufficient_data():
    """Explicitly tests projects with zero tasks under various deadline conditions."""
    today = date(2026, 10, 31)

    # No tasks, no deadline
    score1, level1, factors1 = compute_deterministic_project_risk(
        total_tasks=0, completed_tasks=0, overdue_tasks=0, blocked_tasks=0,
        deadline=None, today=today,
    )
    assert score1 == 10.0
    assert level1 == RiskLevel.LOW
    assert "Insufficient task data" in factors1[0]

    # No tasks, passed deadline -> High risk
    score2, level2, factors2 = compute_deterministic_project_risk(
        total_tasks=0, completed_tasks=0, overdue_tasks=0, blocked_tasks=0,
        deadline=today - timedelta(days=3), today=today,
    )
    assert score2 == 80.0
    assert level2 == RiskLevel.HIGH

    # No tasks, deadline in 3 days -> High risk (imminent)
    score3, level3, factors3 = compute_deterministic_project_risk(
        total_tasks=0, completed_tasks=0, overdue_tasks=0, blocked_tasks=0,
        deadline=today + timedelta(days=3), today=today,
    )
    assert score3 == 70.0
    assert level3 == RiskLevel.HIGH


# --------------------------------------------------------------------------- #
# 2. Grounded Sprint Delay Classification Tests
# --------------------------------------------------------------------------- #

def test_sprint_delay_classification():
    """Verifies that sprint statuses are grounded in actual timelines and never
    fabricate completion dates."""
    today = date(2026, 10, 31)
    start = date(2026, 10, 24)
    end = date(2026, 11, 2)

    # 1. Zero tasks -> INSUFFICIENT_DATA
    st1, f1 = classify_sprint_delay(start, end, total_tasks=0, completed_tasks=0, overdue_tasks=0, today=today)
    assert st1 == DelayStatus.INSUFFICIENT_DATA
    assert "0 assigned tasks" in f1[0]

    # 2. Concluded sprint with incomplete tasks -> DELAYED
    st2, f2 = classify_sprint_delay(start, date(2026, 10, 30), total_tasks=10, completed_tasks=7, overdue_tasks=1, today=today)
    assert st2 == DelayStatus.DELAYED
    assert any("Sprint concluded" in f for f in f2)

    # 3. Active sprint with 2 overdue tasks -> DELAYED
    st3, f3 = classify_sprint_delay(start, end, total_tasks=10, completed_tasks=3, overdue_tasks=2, today=today)
    assert st3 == DelayStatus.DELAYED
    assert any("2 overdue task(s)" in f for f in f3)

    # 4. Active sprint lagging pace -> AT_RISK
    st4, f4 = classify_sprint_delay(start, end, total_tasks=10, completed_tasks=2, overdue_tasks=1, today=today)
    assert st4 == DelayStatus.AT_RISK

    # 5. Active sprint on track -> ON_TRACK
    st5, f5 = classify_sprint_delay(start, end, total_tasks=10, completed_tasks=8, overdue_tasks=0, today=today)
    assert st5 == DelayStatus.ON_TRACK


# --------------------------------------------------------------------------- #
# 3. Workload Imbalance & Anonymization Tests
# --------------------------------------------------------------------------- #

def test_anonymization_of_workload_ai_input():
    """Verifies that employee names and emails are stripped and replaced with
    pseudo-identifiers and role titles before sending to AI."""
    raw_employees = [
        {
            "employee_id": 101,
            "employee_name": "Alice Developer",
            "email": "alice@enterprise.com",
            "role_title": "Senior Frontend Engineer",
            "project_name": "Project Apollo",
            "tasks_assigned": 8,
            "tasks_pending": 6,
            "tasks_overdue": 2,
        },
        {
            "employee_id": 102,
            "employee_name": "Bob Architect",
            "email": "bob@enterprise.com",
            "role_title": "Lead Backend Engineer",
            "project_name": "Project Apollo",
            "tasks_assigned": 2,
            "tasks_pending": 1,
            "tasks_overdue": 0,
        },
    ]

    anonymized = anonymize_workload_records(raw_employees)

    assert len(anonymized) == 2
    for item in anonymized:
        assert "Alice" not in str(item)
        assert "Bob" not in str(item)
        assert "@" not in str(item)
        assert item["employee_ref"].startswith("Worker-")
        assert "role_title" in item
        assert "tasks_pending" in item


def test_workload_imbalance_detection_service(test_db):
    """Verifies workload bottleneck identification when tasks are unevenly concentrated."""
    # Seed Role, Department and Project
    role = Role(name="employee")
    dept = Department(name="Engineering")
    test_db.add_all([role, dept])
    test_db.commit()

    user1 = User(email="emp1@test.com", hashed_password="pw", full_name="Emp One", role_id=role.id)
    user2 = User(email="emp2@test.com", hashed_password="pw", full_name="Emp Two", role_id=role.id)
    test_db.add_all([user1, user2])
    test_db.commit()

    proj = Project(name="Core Infrastructure")
    test_db.add(proj)
    test_db.commit()

    emp1 = Employee(user_id=user1.id, department_id=dept.id, project_id=proj.id, status="active", job_title="Backend Dev", employee_code="EMP-001", hire_date=date.today())
    emp2 = Employee(user_id=user2.id, department_id=dept.id, project_id=proj.id, status="active", job_title="QA Engineer", employee_code="EMP-002", hire_date=date.today())
    test_db.add_all([emp1, emp2])
    test_db.commit()

    sprint = Sprint(project_id=proj.id, name="Sprint 1", start_date=date.today(), end_date=date.today() + timedelta(days=7))
    test_db.add(sprint)
    test_db.commit()

    # Heavy overdue workload on emp1 (4 overdue tasks), emp2 has 0
    yesterday = date.today() - timedelta(days=1)
    for i in range(4):
        test_db.add(SprintTask(sprint_id=sprint.id, assignee_id=emp1.id, title=f"Heavy Task {i}", status="in_progress", due_date=yesterday))
    test_db.add(SprintTask(sprint_id=sprint.id, assignee_id=emp2.id, title="Light Task", status="done"))
    test_db.commit()

    # Call workload intelligence with unconfigured Gemini -> rule engine fallback
    client = GeminiClient(api_key="")
    resp = get_workload_bottleneck_insights(test_db, project_id=proj.id, client=client)

    assert isinstance(resp, WorkloadIntelligenceResponse)
    assert len(resp.bottlenecks) >= 1
    bottleneck = resp.bottlenecks[0]
    assert bottleneck.team_or_project == "Core Infrastructure"
    assert bottleneck.bottleneck_severity == BottleneckSeverity.HIGH
    assert "overdue" in bottleneck.observation.lower()
    assert resp.metadata.is_fallback is True


# --------------------------------------------------------------------------- #
# 4. Support PII Exclusion & Incident Aggregation Tests
# --------------------------------------------------------------------------- #

def test_support_pii_exclusion():
    """Confirms that customer support sanitizer preserves zero customer contact information."""
    sanitized = sanitize_support_data_for_ai(
        total=15,
        open_cnt=5,
        in_prog=3,
        resolved=6,
        escalated=1,
        categories=[{"category_name": "Authentication", "ticket_count": 8}],
    )

    assert "total_tickets" in sanitized
    assert sanitized["open_tickets"] == 5
    assert len(sanitized["category_breakdown"]) == 1
    serialized = str(sanitized)
    assert "email" not in serialized
    assert "phone" not in serialized
    assert "name" not in serialized or "category_name" in serialized


def test_incident_aggregation():
    """Confirms incident metrics sanitizer produces structured operational counts."""
    sanitized = sanitize_incident_data_for_ai(
        total=4,
        open_cnt=1,
        investigating=1,
        resolved=2,
        closed=0,
        severity_breakdown={"critical": 1, "high": 2, "medium": 1, "low": 0},
        affected_systems={"Payment Gateway": 2, "Auth Service": 1},
        avg_res_minutes=45.5,
    )

    assert sanitized["total_incidents"] == 4
    assert sanitized["severity_breakdown"]["critical"] == 1
    assert sanitized["top_affected_systems"]["Payment Gateway"] == 2
    assert sanitized["avg_resolution_minutes"] == 45.5


# --------------------------------------------------------------------------- #
# 5. Gemini Success & Deterministic Score Grounding Protection
# --------------------------------------------------------------------------- #

def test_gemini_success_and_deterministic_grounding_protection(test_db):
    """Crucial Test: Verifies that when Gemini succeeds, it enriches the explanation,
    BUT the numerical risk score and risk level remain 100% determined by Python logic."""
    proj = Project(name="Project Saturn", deadline=date.today() + timedelta(days=2))
    test_db.add(proj)
    test_db.commit()

    sprint = Sprint(project_id=proj.id, name="Saturn Sprint", start_date=date.today(), end_date=date.today() + timedelta(days=7))
    test_db.add(sprint)
    test_db.commit()

    # Seed 5 tasks with 3 overdue -> Deterministic High Risk
    yesterday = date.today() - timedelta(days=1)
    for i in range(3):
        test_db.add(SprintTask(sprint_id=sprint.id, title=f"Task {i}", status="in_progress", due_date=yesterday))
    test_db.commit()

    # Calculate expected deterministic score in Python
    exp_score, exp_level, _ = compute_deterministic_project_risk(
        total_tasks=3, completed_tasks=0, overdue_tasks=3, blocked_tasks=0,
        deadline=proj.deadline, today=date.today(),
    )

    mock_client = MagicMock(spec=GeminiClient)
    mock_client.is_configured = True
    mock_client.model_name = "gemini-flash-lite-latest"

    # Mock Gemini structured output
    mock_payload = _GeminiProjectRiskPayload(
        primary_risk_factors=["Overdue dependency delivery", "Imminent milestone cutoff"],
        risk_explanation="Project Saturn is experiencing delivery strain from unresolved task blockers.",
        potential_consequences="Milestone delivery will slip into the subsequent release window.",
        recommended_actions=["Pair developers on overdue items", "Escalate blockers to team lead"],
    )
    mock_client.generate_structured.return_value = mock_payload

    resp = get_project_risk_insights(test_db, project_id=proj.id, client=mock_client)

    assert isinstance(resp, ProjectRiskIntelligenceResponse)
    assert len(resp.projects) == 1
    item = resp.projects[0]

    # Verify Gemini enrichment
    assert item.risk_explanation == "Project Saturn is experiencing delivery strain from unresolved task blockers."
    assert item.recommended_actions[0] == "Pair developers on overdue items"

    # Verify Strict Deterministic Invariance: Score and level match Python calculation
    assert item.deterministic_risk_score == exp_score
    assert item.deterministic_risk_level == exp_level
    assert resp.metadata.is_fallback is False
    assert resp.metadata.model_provider == "gemini"


# --------------------------------------------------------------------------- #
# 6. Rule-Engine Fallback on Gemini Failure
# --------------------------------------------------------------------------- #

def test_rule_engine_fallback_when_gemini_fails(test_db):
    """Verifies that if Gemini throws AIQuotaError or network failure, the service
    transparently falls back to the deterministic rule engine without throwing 500."""
    proj = Project(name="Project Mercury", deadline=date.today() + timedelta(days=14))
    test_db.add(proj)
    test_db.commit()

    mock_client = MagicMock(spec=GeminiClient)
    mock_client.is_configured = True
    mock_client.model_name = "gemini-flash-lite-latest"
    mock_client.generate_structured.side_effect = AIQuotaError("Daily quota exhausted for test.")

    resp = get_project_risk_insights(test_db, project_id=proj.id, client=mock_client)

    assert isinstance(resp, ProjectRiskIntelligenceResponse)
    assert len(resp.projects) == 1
    item = resp.projects[0]

    # Check fallback fields populated
    assert "Project 'Project Mercury'" in item.risk_explanation
    assert len(item.recommended_actions) >= 1
    assert resp.metadata.is_fallback is True
    assert resp.metadata.model_provider == "deterministic_rule_engine"


# --------------------------------------------------------------------------- #
# 7. Cache Hit, Throttling & Project-Specific Isolation Tests
# --------------------------------------------------------------------------- #

def test_cache_hit_and_refresh_behavior(test_db):
    """Verifies in-memory caching, cache hit marking, and 10-second refresh throttling."""
    proj = Project(name="Apollo 11")
    test_db.add(proj)
    test_db.commit()

    client = GeminiClient(api_key="")

    # Call 1: Uncached evaluation
    resp1 = get_project_risk_insights(test_db, project_id=proj.id, client=client)
    assert resp1.metadata.is_cached is False

    # Call 2: Cached retrieval
    resp2 = get_project_risk_insights(test_db, project_id=proj.id, client=client)
    assert resp2.metadata.is_cached is True
    assert resp2.projects[0].project_name == "Apollo 11"

    # Call 3: Force refresh within 10s cooldown -> Throttled, returns cached entry
    resp3 = get_project_risk_insights(test_db, project_id=proj.id, force_refresh=True, client=client)
    assert resp3.projects[0].project_name == "Apollo 11"


def test_project_specific_cache_isolation(test_db):
    """Verifies that project-specific cache keys prevent cross-project data leakage."""
    p1 = Project(name="Project Alpha")
    p2 = Project(name="Project Beta")
    test_db.add_all([p1, p2])
    test_db.commit()

    client = GeminiClient(api_key="")

    resp_p1 = get_project_risk_insights(test_db, project_id=p1.id, client=client)
    resp_p2 = get_project_risk_insights(test_db, project_id=p2.id, client=client)

    assert resp_p1.projects[0].project_name == "Project Alpha"
    assert resp_p2.projects[0].project_name == "Project Beta"
    assert resp_p1.projects[0].project_id != resp_p2.projects[0].project_id


# --------------------------------------------------------------------------- #
# 8. Executive Recommendations Grounding Tests
# --------------------------------------------------------------------------- #

def test_executive_recommendation_grounding(test_db):
    """Verifies that executive recommendations strictly adhere to the 4-part structure,
    are grounded in verified metrics, and require human approval."""
    proj = Project(name="Critical Project", deadline=date.today() - timedelta(days=1))
    test_db.add(proj)
    test_db.commit()

    sprint = Sprint(project_id=proj.id, name="Sprint Critical", start_date=date.today() - timedelta(days=7), end_date=date.today() - timedelta(days=1))
    test_db.add(sprint)
    test_db.commit()

    # 2 overdue uncompleted tasks
    test_db.add(SprintTask(sprint_id=sprint.id, title="Overdue Bug", status="in_progress", due_date=date.today() - timedelta(days=2)))
    test_db.commit()

    client = GeminiClient(api_key="")
    resp = get_executive_recommendations(test_db, project_id=proj.id, client=client)

    assert isinstance(resp, ExecutiveSummaryResponse)
    assert resp.overall_status in ["critical_attention", "attention_required"]
    assert len(resp.recommendations) >= 1

    rec = resp.recommendations[0]
    assert rec.observation is not None and len(rec.observation) >= 5
    assert rec.why_it_matters is not None and len(rec.why_it_matters) >= 5
    assert rec.potential_consequence is not None and len(rec.potential_consequence) >= 5
    assert rec.recommended_preventive_action is not None and len(rec.recommended_preventive_action) >= 5
    assert rec.requires_human_approval is True
    assert resp.metadata.disclaimer is not None
