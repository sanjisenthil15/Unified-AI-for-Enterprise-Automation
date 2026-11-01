"""
modules/intelligence/service.py

Core Business Logic for Phase 3.2: AI-Powered Enterprise Intelligence Service.

Architectural Principles & Grounding Rules:
  1. Deterministic Calculation: Numerical risk scores (0.0-100.0) and risk levels
     (LOW, MEDIUM, HIGH) are calculated strictly by Python backend algorithms.
     Gemini is used exclusively to explain verified evidence and recommend actions.
     Gemini NEVER calculates, changes, or overrides numerical scores.
  2. Grounded Sprint Assessment: Delay classifications are derived from verifiable
     timelines, task completion rates, and overdue metrics. No completion dates
     are fabricated.
  3. Strict Data Anonymization: Employee names, personal emails, phone numbers,
     customer contact details, and ticket descriptions are strictly excluded from
     all AI prompts. Only anonymized role identifiers and aggregated counts are transmitted.
  4. Quota-Resilient Fallbacks: When Gemini is unavailable, unconfigured, or has
     exhausted daily quota, a deterministic rule-engine seamlessly synthesizes
     structured advisory responses, transparently flagging `metadata.is_fallback = True`.
  5. Scope-Aware In-Memory Caching: Intelligence responses are cached for 30 minutes
     with per-project and per-organization keys, duplicate evaluation serialization,
     and 10-second manual refresh throttling.
"""

from datetime import date, datetime, timedelta, timezone
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, TypeVar
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from config.database import Base
from models.employee import Employee
from models.incident import Incident
from models.project import Project
from models.sprint import Sprint
from models.sprint_task import SprintTask
from models.ticket import SupportCategory, SupportTicket
from modules.customer_support import service as cs_service

from modules.intelligence.ai_client import (
    AIClientError,
    AIConfigError,
    AIParseError,
    AIQuotaError,
    AIValidationError,
    GeminiClient,
)
from modules.intelligence.cache import DEFAULT_TTL_SECONDS, intelligence_cache
from modules.intelligence.schemas import (
    AIMetadata,
    BottleneckSeverity,
    DelayStatus,
    ExecutiveRecommendationItem,
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

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# --------------------------------------------------------------------------- #
# Helper Pydantic Schemas for Structured Gemini Outputs
# --------------------------------------------------------------------------- #

class _GeminiProjectRiskPayload(BaseModel):
    primary_risk_factors: List[str] = Field(default_factory=list, max_length=10)
    risk_explanation: str = Field(..., min_length=10, max_length=1000)
    potential_consequences: str = Field(..., min_length=5, max_length=500)
    recommended_actions: List[str] = Field(default_factory=list, max_length=6)


class _GeminiSprintDelayPayload(BaseModel):
    delay_explanation: str = Field(..., min_length=10, max_length=1000)
    contributing_factors: List[str] = Field(default_factory=list, max_length=10)
    recommended_mitigations: List[str] = Field(default_factory=list, max_length=6)


class _GeminiWorkloadPayload(BaseModel):
    bottlenecks: List[WorkloadBottleneckItem] = Field(default_factory=list)


class _GeminiOperationsPayload(BaseModel):
    support_insights: List[str] = Field(default_factory=list, max_length=10)
    incident_insights: List[str] = Field(default_factory=list, max_length=10)
    operational_summary: str = Field(..., min_length=10, max_length=1000)


# --------------------------------------------------------------------------- #
# 1. Deterministic Calculation Engines
# --------------------------------------------------------------------------- #

def compute_deterministic_project_risk(
    total_tasks: int,
    completed_tasks: int,
    overdue_tasks: int,
    blocked_tasks: int,
    deadline: Optional[date],
    today: Optional[date] = None,
) -> Tuple[float, RiskLevel, List[str]]:
    """Deterministically computes numerical project risk score (0.0 to 100.0),
    risk level (LOW, MEDIUM, HIGH), and detected risk factor statements.

    Formulation:
      - Overdue tasks factor: Up to 45.0 points based on overdue-to-total ratio.
      - Deadline & Pacing factor: Up to 40.0 points based on remaining time vs uncompleted work.
      - Blocked tasks factor: Up to 15.0 points based on blocked tasks ratio.
    """
    if today is None:
        today = date.today()

    factors: List[str] = []

    # Edge Case: Project has no tasks recorded
    if total_tasks <= 0:
        if deadline is None:
            return 10.0, RiskLevel.LOW, ["Insufficient task data: 0 tasks currently defined."]
        if deadline < today:
            return 80.0, RiskLevel.HIGH, [
                "Zero tasks defined and the target milestone deadline has already passed."
            ]
        days_left = (deadline - today).days
        if days_left <= 7:
            return 70.0, RiskLevel.HIGH, [
                f"Zero tasks completed with target milestone deadline imminent in {days_left} day(s)."
            ]
        return 20.0, RiskLevel.LOW, [
            f"Zero tasks created yet; target milestone deadline is in {days_left} days."
        ]

    # Component 1: Overdue Task Weight (0.0 - 45.0)
    overdue_ratio = overdue_tasks / total_tasks
    overdue_points = min(45.0, overdue_ratio * 100.0)
    if overdue_tasks > 0:
        factors.append(f"{overdue_tasks} overdue task(s) ({round(overdue_ratio * 100, 1)}% of total work).")

    # Component 2: Deadline & Pacing Weight (0.0 - 45.0)
    uncompleted_ratio = max(0.0, (total_tasks - completed_tasks) / total_tasks)
    deadline_points = 0.0

    if deadline is not None:
        days_remaining = (deadline - today).days
        if days_remaining < 0:
            deadline_points = 45.0
            factors.append(
                f"Project deadline passed {abs(days_remaining)} day(s) ago with "
                f"{total_tasks - completed_tasks} task(s) uncompleted."
            )
        elif days_remaining == 0:
            deadline_points = min(45.0, 35.0 + (uncompleted_ratio * 10.0))
            factors.append(
                f"Project deadline is today with {total_tasks - completed_tasks} task(s) uncompleted."
            )
        elif days_remaining <= 7:
            # Imminent deadline
            urgency_factor = (1.0 - (days_remaining / 7.0)) * 20.0
            deadline_points = min(45.0, urgency_factor + (uncompleted_ratio * 25.0))
            factors.append(
                f"Approaching deadline in {days_remaining} day(s) with "
                f"{round(uncompleted_ratio * 100, 1)}% remaining work."
            )
        elif days_remaining <= 14:
            deadline_points = min(35.0, 10.0 + (uncompleted_ratio * 25.0))
            if uncompleted_ratio > 0.5:
                factors.append(
                    f"Deadline in {days_remaining} days with substantial pending tasks "
                    f"({round(uncompleted_ratio * 100, 1)}% incomplete)."
                )
        else:
            deadline_points = uncompleted_ratio * 20.0
    else:
        # No explicit project deadline: weight based on overall uncompleted proportion
        deadline_points = uncompleted_ratio * 25.0
        if uncompleted_ratio > 0.6:
            factors.append(
                f"High pending workload: {round(uncompleted_ratio * 100, 1)}% incomplete without explicit deadline."
            )

    # Component 3: Blocked Tasks Weight (0.0 - 15.0)
    blocked_ratio = blocked_tasks / total_tasks
    blocked_points = min(15.0, blocked_ratio * 50.0)
    if blocked_tasks > 0:
        factors.append(f"{blocked_tasks} blocked task(s) requiring immediate impediment removal.")

    # Calculate final score
    raw_score = overdue_points + deadline_points + blocked_points
    risk_score = round(min(100.0, max(0.0, raw_score)), 1)

    # Classify Risk Level
    if risk_score >= 70.0:
        risk_level = RiskLevel.HIGH
    elif risk_score >= 35.0:
        risk_level = RiskLevel.MEDIUM
    else:
        risk_level = RiskLevel.LOW

    if not factors:
        factors.append(f"Project execution healthy: {completed_tasks}/{total_tasks} tasks completed with 0 overdue.")

    return risk_score, risk_level, factors


def classify_sprint_delay(
    start_date: date,
    end_date: date,
    total_tasks: int,
    completed_tasks: int,
    overdue_tasks: int,
    today: Optional[date] = None,
) -> Tuple[DelayStatus, List[str]]:
    """Deterministically classifies sprint delay status based on dates,
    task completion ratio, and overdue count. Never hallucinates completion dates."""
    if today is None:
        today = date.today()

    factors: List[str] = []

    if total_tasks == 0:
        return DelayStatus.INSUFFICIENT_DATA, ["Sprint has 0 assigned tasks."]

    remaining_tasks = total_tasks - completed_tasks
    completion_pct = round((completed_tasks / total_tasks) * 100.0, 1)

    # Past Sprint Deadline
    if today > end_date:
        if remaining_tasks > 0:
            factors.append(
                f"Sprint concluded on {end_date.isoformat()} with {remaining_tasks} uncompleted task(s)."
            )
            if overdue_tasks > 0:
                factors.append(f"{overdue_tasks} task(s) missed their scheduled due dates.")
            return DelayStatus.DELAYED, factors
        factors.append("Sprint successfully closed with 100% completion.")
        return DelayStatus.ON_TRACK, factors

    # Active Ongoing Sprint
    total_days = max(1, (end_date - start_date).days)
    elapsed_days = max(0, (today - start_date).days)
    timeline_pct = round(min(100.0, (elapsed_days / total_days) * 100.0), 1)

    if overdue_tasks >= 2 or (overdue_tasks > 0 and timeline_pct >= 80.0 and completion_pct < 50.0):
        factors.append(f"{overdue_tasks} overdue task(s) during active sprint cycle.")
        factors.append(f"Progress ({completion_pct}%) significantly lags timeline elapsed ({timeline_pct}%).")
        return DelayStatus.DELAYED, factors

    if overdue_tasks > 0 or (timeline_pct >= 50.0 and completion_pct < (timeline_pct - 20.0)):
        if overdue_tasks > 0:
            factors.append(f"{overdue_tasks} task(s) currently overdue.")
        factors.append(
            f"Completion rate ({completion_pct}%) is lagging sprint timeline progress ({timeline_pct}% elapsed)."
        )
        return DelayStatus.AT_RISK, factors

    factors.append(
        f"Pace healthy: {completed_tasks}/{total_tasks} completed ({completion_pct}%) vs {timeline_pct}% timeline elapsed."
    )
    return DelayStatus.ON_TRACK, factors


# --------------------------------------------------------------------------- #
# 2. Privacy & Anonymization Sanitizers
# --------------------------------------------------------------------------- #

def anonymize_workload_records(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sanitizes workload data for AI prompt payloads.
    Replaces real employee names and emails with role titles and pseudo-identifiers."""
    anonymized = []
    for idx, item in enumerate(raw_items, 1):
        anonymized.append({
            "employee_ref": f"Worker-{idx}",
            "role_title": item.get("role_title") or "Engineering Team Member",
            "project_name": item.get("project_name") or "Unassigned",
            "tasks_assigned": item.get("tasks_assigned", 0),
            "tasks_pending": item.get("tasks_pending", 0),
            "tasks_overdue": item.get("tasks_overdue", 0),
        })
    return anonymized


def sanitize_support_data_for_ai(
    total: int,
    open_cnt: int,
    in_prog: int,
    resolved: int,
    escalated: int,
    categories: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Ensures customer support data passed to AI contains strictly aggregated
    counts and category statistics with zero customer PII or raw messages."""
    return {
        "total_tickets": total,
        "open_tickets": open_cnt,
        "in_progress_tickets": in_prog,
        "resolved_tickets": resolved,
        "escalated_tickets": escalated,
        "category_breakdown": [
            {"category": c.get("category_name", "General"), "count": c.get("ticket_count", 0)}
            for c in categories
        ],
    }


def sanitize_incident_data_for_ai(
    total: int,
    open_cnt: int,
    investigating: int,
    resolved: int,
    closed: int,
    severity_breakdown: Dict[str, int],
    affected_systems: Dict[str, int],
    avg_res_minutes: Optional[float],
) -> Dict[str, Any]:
    """Ensures incident data passed to AI contains strictly operational
    aggregates and affected system totals with zero user identifiers."""
    return {
        "total_incidents": total,
        "open_incidents": open_cnt,
        "investigating_incidents": investigating,
        "resolved_incidents": resolved,
        "closed_incidents": closed,
        "severity_breakdown": severity_breakdown,
        "top_affected_systems": affected_systems,
        "avg_resolution_minutes": avg_res_minutes,
    }


# --------------------------------------------------------------------------- #
# 3. Deterministic Rule-Engine Fallback Synthesizers
# --------------------------------------------------------------------------- #

def _build_project_risk_fallback_item(
    project_id: int,
    project_name: str,
    risk_score: float,
    risk_level: RiskLevel,
    factors: List[str],
    total_tasks: int,
    overdue_tasks: int,
    days_remaining: Optional[int],
) -> ProjectRiskExplanationItem:
    """Constructs a deterministic, metric-grounded explanation when Gemini is unavailable."""
    if risk_level == RiskLevel.HIGH:
        explanation = (
            f"Project '{project_name}' requires executive intervention with a deterministic risk score of "
            f"{risk_score}/100. There are {overdue_tasks} overdue tasks out of {total_tasks} total deliverables."
        )
        consequences = (
            "Sprint targets will miss the scheduled milestone date, and engineering velocity "
            "will be blocked unless work is rebalanced."
        )
        actions = [
            "Reallocate overdue tasks across available team members.",
            "Schedule a milestone triage review with the team leader.",
            "De-scope non-critical sprint backlog items.",
        ]
    elif risk_level == RiskLevel.MEDIUM:
        explanation = (
            f"Project '{project_name}' is experiencing moderate delivery strain with a risk score of "
            f"{risk_score}/100. Pending deliverables require close tracking to prevent deadline slippage."
        )
        consequences = (
            "Potential delivery delay if current overdue items are not resolved within the current cycle."
        )
        actions = [
            "Monitor daily standup progress on in-progress items.",
            "Address any blocked task dependencies.",
        ]
    else:
        explanation = (
            f"Project '{project_name}' is progressing normally with a low risk score of {risk_score}/100. "
            f"Deliverables are aligned with milestone expectations."
        )
        consequences = "No immediate delivery risk detected under current workload parameters."
        actions = [
            "Maintain current sprint cadence and milestone monitoring.",
        ]

    return ProjectRiskExplanationItem(
        project_id=project_id,
        project_name=project_name,
        deterministic_risk_level=risk_level,
        deterministic_risk_score=risk_score,
        primary_risk_factors=factors[:5],
        risk_explanation=explanation,
        potential_consequences=consequences,
        recommended_actions=actions,
    )


def _build_sprint_delay_fallback_item(
    sprint_id: int,
    sprint_name: str,
    project_name: str,
    delay_status: DelayStatus,
    factors: List[str],
    total_tasks: int,
    completed_tasks: int,
    overdue_tasks: int,
) -> SprintDelayExplanationItem:
    """Constructs a grounded sprint delay explanation without LLM hallucination."""
    completion_pct = round((completed_tasks / total_tasks) * 100.0, 1) if total_tasks > 0 else 0.0

    if delay_status == DelayStatus.DELAYED:
        explanation = (
            f"Sprint '{sprint_name}' in project '{project_name}' is classified as DELAYED. "
            f"Only {completed_tasks} of {total_tasks} tasks ({completion_pct}%) are finished, and "
            f"{overdue_tasks} tasks are currently overdue."
        )
        mitigations = [
            "Conduct an immediate blocker clearing session with task assignees.",
            "Roll incomplete non-essential tasks into the subsequent sprint backlog.",
            "Enforce strict priority on overdue items.",
        ]
    elif delay_status == DelayStatus.AT_RISK:
        explanation = (
            f"Sprint '{sprint_name}' is AT RISK of missing its completion target. "
            f"Work completed ({completion_pct}%) is tracking behind the elapsed schedule timeline."
        )
        mitigations = [
            "Pair developers on pending tasks.",
            "Reassign unstarted tasks if team capacity allows.",
        ]
    elif delay_status == DelayStatus.INSUFFICIENT_DATA:
        explanation = f"Sprint '{sprint_name}' has 0 tasks recorded; insufficient data to calculate delay trajectory."
        mitigations = ["Add sprint backlog tasks and assign team members."]
    else:
        explanation = (
            f"Sprint '{sprint_name}' is ON TRACK. Completion rate ({completion_pct}%) matches expected timeline velocity."
        )
        mitigations = ["Continue standard sprint delivery cadence."]

    return SprintDelayExplanationItem(
        sprint_id=sprint_id,
        sprint_name=sprint_name,
        project_name=project_name,
        delay_status=delay_status,
        delay_explanation=explanation,
        contributing_factors=factors[:5],
        recommended_mitigations=mitigations,
    )


# --------------------------------------------------------------------------- #
# 4. Intelligence Service Public Methods
# --------------------------------------------------------------------------- #

def get_project_risk_insights(
    db: Session,
    project_id: Optional[int] = None,
    force_refresh: bool = False,
    client: Optional[GeminiClient] = None,
) -> ProjectRiskIntelligenceResponse:
    """Evaluates project risk deterministically and supplements with Gemini root-cause
    explanations and actionable recommendations.

    Enforces:
      - Deterministic risk score & level calculated in Python.
      - Gemini never calculates or overrides numerical scores.
      - Graceful fallback to deterministic rule engine if Gemini is unavailable.
      - 30-minute caching with scope-aware keys and 10s refresh cooldown.
    """
    cache_key = (
        f"intelligence:project:{project_id}:risk"
        if project_id is not None
        else "intelligence:org:project_risks"
    )

    if force_refresh:
        allowed, remaining = intelligence_cache.check_refresh_throttle(cache_key)
        if not allowed:
            cached = intelligence_cache.get(cache_key)
            if cached:
                logger.info("Refresh throttled for '%s' (%.1fs remaining). Returning cached.", cache_key, remaining)
                return cached

    def _evaluator() -> ProjectRiskIntelligenceResponse:
        today = date.today()
        projects_query = db.query(Project)
        if project_id is not None:
            projects_query = projects_query.filter(Project.id == project_id)
        projects = projects_query.order_by(Project.id).all()

        ai_client = client or GeminiClient()
        is_gemini_active = ai_client.is_configured
        items: List[ProjectRiskExplanationItem] = []
        gemini_succeeded = False

        for proj in projects:
            # Query tasks for this project
            tasks = (
                db.query(SprintTask)
                .join(Sprint, Sprint.id == SprintTask.sprint_id)
                .filter(Sprint.project_id == proj.id)
                .all()
            )
            tasks_total = len(tasks)
            tasks_done = sum(1 for t in tasks if t.status == "done")
            tasks_blocked = sum(1 for t in tasks if t.status == "blocked")
            tasks_overdue = sum(
                1 for t in tasks
                if t.status != "done" and t.due_date is not None and t.due_date < today
            )

            # 1. Deterministic Calculation (Strict Boundary)
            score, level, factors = compute_deterministic_project_risk(
                total_tasks=tasks_total,
                completed_tasks=tasks_done,
                overdue_tasks=tasks_overdue,
                blocked_tasks=tasks_blocked,
                deadline=proj.deadline,
                today=today,
            )

            days_remaining = (proj.deadline - today).days if proj.deadline else None

            # 2. Attempt Gemini Explanation (if configured)
            explanation_item: Optional[ProjectRiskExplanationItem] = None
            if is_gemini_active:
                prompt = (
                    f"You are an enterprise operations advisor. A deterministic algorithm has evaluated project risk.\n"
                    f"Project: {proj.name} (ID: {proj.id})\n"
                    f"Verified Deterministic Risk Score: {score}/100 (Level: {level.value.upper()})\n"
                    f"Verified Metrics: Total Tasks={tasks_total}, Completed={tasks_done}, "
                    f"Overdue={tasks_overdue}, Blocked={tasks_blocked}, Deadline={proj.deadline}\n"
                    f"Detected Factors:\n" + "\n".join(f"- {f}" for f in factors) + "\n\n"
                    f"Instructions:\n"
                    f"1. Explain the root causes driving this {level.value.upper()} risk level based ONLY on the metrics.\n"
                    f"2. Describe potential operational consequences if left unaddressed.\n"
                    f"3. Provide 2-4 concrete, preventive recommendations for leadership.\n"
                    f"4. Do NOT calculate or change any numerical score."
                )
                try:
                    payload = ai_client.generate_structured(prompt, _GeminiProjectRiskPayload)
                    explanation_item = ProjectRiskExplanationItem(
                        project_id=proj.id,
                        project_name=proj.name,
                        deterministic_risk_level=level,  # Strictly deterministic
                        deterministic_risk_score=score,  # Strictly deterministic
                        primary_risk_factors=payload.primary_risk_factors or factors[:5],
                        risk_explanation=payload.risk_explanation,
                        potential_consequences=payload.potential_consequences,
                        recommended_actions=payload.recommended_actions,
                    )
                    gemini_succeeded = True
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Gemini risk explanation failed for project %d: %s. Using rule fallback.", proj.id, exc)
                    explanation_item = None

            # Fallback if Gemini unavailable or failed
            if explanation_item is None:
                explanation_item = _build_project_risk_fallback_item(
                    project_id=proj.id,
                    project_name=proj.name,
                    risk_score=score,
                    risk_level=level,
                    factors=factors,
                    total_tasks=tasks_total,
                    overdue_tasks=tasks_overdue,
                    days_remaining=days_remaining,
                )

            items.append(explanation_item)

        metadata = AIMetadata(
            model_provider="gemini" if gemini_succeeded else "deterministic_rule_engine",
            model_name=getattr(ai_client, "model_name", "gemini-flash-lite-latest") if gemini_succeeded else "rule_engine_v1",
            is_fallback=not gemini_succeeded,
        )

        return ProjectRiskIntelligenceResponse(
            projects=items,
            metadata=metadata,
        )

    result, is_cached = intelligence_cache.get_or_evaluate(
        key=cache_key,
        evaluator_fn=_evaluator,
        ttl=DEFAULT_TTL_SECONDS,
        force_refresh=force_refresh,
    )
    result.metadata.is_cached = is_cached
    return result


def get_sprint_delay_insights(
    db: Session,
    project_id: Optional[int] = None,
    sprint_id: Optional[int] = None,
    force_refresh: bool = False,
    client: Optional[GeminiClient] = None,
) -> SprintDelayIntelligenceResponse:
    """Analyzes sprint delivery status against scheduled milestones.
    Never invents completion dates or fabricates predictions."""
    if sprint_id is not None:
        cache_key = f"intelligence:sprint:{sprint_id}:delay"
    elif project_id is not None:
        cache_key = f"intelligence:project:{project_id}:sprint_delays"
    else:
        cache_key = "intelligence:org:sprint_delays"

    if force_refresh:
        allowed, remaining = intelligence_cache.check_refresh_throttle(cache_key)
        if not allowed:
            cached = intelligence_cache.get(cache_key)
            if cached:
                return cached

    def _evaluator() -> SprintDelayIntelligenceResponse:
        today = date.today()
        sprints_query = db.query(Sprint).options(joinedload(Sprint.project))
        if sprint_id is not None:
            sprints_query = sprints_query.filter(Sprint.id == sprint_id)
        elif project_id is not None:
            sprints_query = sprints_query.filter(Sprint.project_id == project_id)

        # Focus on active and recently planned sprints
        sprints = sprints_query.order_by(Sprint.end_date.desc()).all()

        ai_client = client or GeminiClient()
        is_gemini_active = ai_client.is_configured
        items: List[SprintDelayExplanationItem] = []

        for spr in sprints:
            tasks = db.query(SprintTask).filter(SprintTask.sprint_id == spr.id).all()
            total_tasks = len(tasks)
            completed_tasks = sum(1 for t in tasks if t.status == "done")
            overdue_tasks = sum(
                1 for t in tasks
                if t.status != "done" and t.due_date is not None and t.due_date < today
            )

            delay_status, factors = classify_sprint_delay(
                start_date=spr.start_date,
                end_date=spr.end_date,
                total_tasks=total_tasks,
                completed_tasks=completed_tasks,
                overdue_tasks=overdue_tasks,
                today=today,
            )

            p_name = spr.project.name if spr.project else "General Project"

            explanation_item: Optional[SprintDelayExplanationItem] = None
            if is_gemini_active:
                prompt = (
                    f"You are a technical project management assistant.\n"
                    f"Sprint: '{spr.name}' (Project: '{p_name}')\n"
                    f"Timeline: Start {spr.start_date} to End {spr.end_date}\n"
                    f"Deterministic Status: {delay_status.value.upper()}\n"
                    f"Tasks: Total={total_tasks}, Completed={completed_tasks}, Overdue={overdue_tasks}\n"
                    f"Observed Factors:\n" + "\n".join(f"- {f}" for f in factors) + "\n\n"
                    f"Instructions:\n"
                    f"1. Explain the current status based ONLY on these metrics.\n"
                    f"2. Suggest 2-3 practical mitigations.\n"
                    f"3. Do NOT predict or invent a specific completion date."
                )
                try:
                    payload = ai_client.generate_structured(prompt, _GeminiSprintDelayPayload)
                    explanation_item = SprintDelayExplanationItem(
                        sprint_id=spr.id,
                        sprint_name=spr.name,
                        project_name=p_name,
                        delay_status=delay_status,
                        delay_explanation=payload.delay_explanation,
                        contributing_factors=payload.contributing_factors or factors[:5],
                        recommended_mitigations=payload.recommended_mitigations,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Gemini sprint delay failed for sprint %d: %s. Using rule fallback.", spr.id, exc)
                    explanation_item = None

            if explanation_item is None:
                explanation_item = _build_sprint_delay_fallback_item(
                    sprint_id=spr.id,
                    sprint_name=spr.name,
                    project_name=p_name,
                    delay_status=delay_status,
                    factors=factors,
                    total_tasks=total_tasks,
                    completed_tasks=completed_tasks,
                    overdue_tasks=overdue_tasks,
                )

            items.append(explanation_item)

        metadata = AIMetadata(
            model_provider="gemini" if is_gemini_active else "deterministic_rule_engine",
            model_name=ai_client.model_name if is_gemini_active else "rule_engine_v1",
            is_fallback=not is_gemini_active,
        )

        return SprintDelayIntelligenceResponse(
            sprints=items,
            metadata=metadata,
        )

    result, is_cached = intelligence_cache.get_or_evaluate(
        key=cache_key,
        evaluator_fn=_evaluator,
        ttl=DEFAULT_TTL_SECONDS,
        force_refresh=force_refresh,
    )
    result.metadata.is_cached = is_cached
    return result


def get_workload_bottleneck_insights(
    db: Session,
    project_id: Optional[int] = None,
    force_refresh: bool = False,
    client: Optional[GeminiClient] = None,
) -> WorkloadIntelligenceResponse:
    """Identifies role-level workload bottlenecks and distribution imbalances.
    Enforces privacy by anonymizing employee identities and forbidding subjective productivity ratings."""
    cache_key = (
        f"intelligence:project:{project_id}:workload"
        if project_id is not None
        else "intelligence:org:workload"
    )

    if force_refresh:
        allowed, remaining = intelligence_cache.check_refresh_throttle(cache_key)
        if not allowed:
            cached = intelligence_cache.get(cache_key)
            if cached:
                return cached

    def _evaluator() -> WorkloadIntelligenceResponse:
        today = date.today()
        emp_query = db.query(Employee).filter(Employee.deleted_at.is_(None))
        if project_id is not None:
            emp_query = emp_query.filter(Employee.project_id == project_id)

        employees = emp_query.options(
            joinedload(Employee.project),
            joinedload(Employee.department),
        ).all()

        emp_ids = [e.id for e in employees]
        tasks = db.query(SprintTask).filter(SprintTask.assignee_id.in_(emp_ids)).all() if emp_ids else []

        tasks_by_emp: Dict[int, List[SprintTask]] = {eid: [] for eid in emp_ids}
        for t in tasks:
            if t.assignee_id in tasks_by_emp:
                tasks_by_emp[t.assignee_id].append(t)

        # Aggregate by team/project
        team_buckets: Dict[str, List[Dict[str, Any]]] = {}
        for emp in employees:
            team_name = emp.project.name if emp.project else "Unassigned Staff"
            e_tasks = tasks_by_emp.get(emp.id, [])
            pending = sum(1 for t in e_tasks if t.status != "done")
            overdue = sum(
                1 for t in e_tasks
                if t.status != "done" and t.due_date is not None and t.due_date < today
            )
            role = emp.job_title if hasattr(emp, "job_title") and emp.job_title else "Software Engineer"

            if team_name not in team_buckets:
                team_buckets[team_name] = []
            team_buckets[team_name].append({
                "employee_id": emp.id,
                "role_title": role,
                "project_name": team_name,
                "tasks_assigned": len(e_tasks),
                "tasks_pending": pending,
                "tasks_overdue": overdue,
            })

        bottleneck_items: List[WorkloadBottleneckItem] = []
        ai_client = client or GeminiClient()
        is_gemini_active = ai_client.is_configured

        for team_name, members in team_buckets.items():
            total_members = len(members)
            total_pending = sum(m["tasks_pending"] for m in members)
            total_overdue = sum(m["tasks_overdue"] for m in members)
            avg_pending = (total_pending / total_members) if total_members > 0 else 0.0

            # Find overburdened roles
            overburdened = [
                m for m in members
                if (m["tasks_pending"] > max(3, avg_pending * 1.5)) or (m["tasks_overdue"] >= 2)
            ]
            affected_roles = list({m["role_title"] for m in overburdened})

            # Determine severity deterministically
            if total_overdue >= 4 or (total_pending > 12 and len(overburdened) >= 2):
                severity = BottleneckSeverity.HIGH
            elif total_overdue >= 1 or len(overburdened) >= 1:
                severity = BottleneckSeverity.MEDIUM
            else:
                severity = BottleneckSeverity.LOW

            if severity == BottleneckSeverity.LOW and total_members > 0:
                obs = f"Workload in '{team_name}' is balanced across {total_members} team members with 0 overdue tasks."
                action = "Maintain current sprint allocation."
            else:
                obs = (
                    f"Team '{team_name}' has {len(overburdened)} member(s) with concentrated pending workload "
                    f"({total_overdue} total overdue tasks across team)."
                )
                action = "Reassign queued tasks to lower-utilization team members and unblock overdue deliverables."

            # Supplement with Gemini if active and meaningful bottleneck exists
            item: Optional[WorkloadBottleneckItem] = None
            if is_gemini_active and severity != BottleneckSeverity.LOW:
                anonymized_members = anonymize_workload_records(members)
                prompt = (
                    f"You are a workforce operations analyst. Analyze the following team workload:\n"
                    f"Team: '{team_name}' (Total Members: {total_members})\n"
                    f"Severity Classification: {severity.value.upper()}\n"
                    f"Anonymized Member Allocation:\n"
                    + "\n".join(
                        f"- {m['employee_ref']} ({m['role_title']}): "
                        f"Pending={m['tasks_pending']}, Overdue={m['tasks_overdue']}"
                        for m in anonymized_members
                    )
                    + "\n\n"
                    f"Instructions:\n"
                    f"1. Summarize the observed workload imbalance in 1-2 sentences.\n"
                    f"2. Suggest an operational balancing action.\n"
                    f"3. Do NOT mention individual employee names or generate subjective productivity ratings."
                )
                try:
                    payload = ai_client.generate_structured(
                        prompt,
                        WorkloadBottleneckItem,
                        system_instruction="Analyze workload distribution at the team level without personal surveillance.",
                    )
                    item = WorkloadBottleneckItem(
                        team_or_project=team_name,
                        bottleneck_severity=severity,
                        observation=payload.observation,
                        affected_roles=affected_roles or ["Engineering Staff"],
                        suggested_balancing_action=payload.suggested_balancing_action,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Gemini workload analysis failed: %s. Using rule fallback.", exc)
                    item = None

            if item is None:
                item = WorkloadBottleneckItem(
                    team_or_project=team_name,
                    bottleneck_severity=severity,
                    observation=obs,
                    affected_roles=affected_roles or ["Engineering Staff"],
                    suggested_balancing_action=action,
                )
            bottleneck_items.append(item)

        if not bottleneck_items:
            bottleneck_items.append(
                WorkloadBottleneckItem(
                    team_or_project="Organization",
                    bottleneck_severity=BottleneckSeverity.LOW,
                    observation="No active projects or workload bottlenecks detected.",
                    affected_roles=[],
                    suggested_balancing_action="Continue current workforce allocation.",
                )
            )

        metadata = AIMetadata(
            model_provider="gemini" if is_gemini_active else "deterministic_rule_engine",
            model_name=ai_client.model_name if is_gemini_active else "rule_engine_v1",
            is_fallback=not is_gemini_active,
        )

        return WorkloadIntelligenceResponse(
            bottlenecks=bottleneck_items,
            metadata=metadata,
        )

    result, is_cached = intelligence_cache.get_or_evaluate(
        key=cache_key,
        evaluator_fn=_evaluator,
        ttl=DEFAULT_TTL_SECONDS,
        force_refresh=force_refresh,
    )
    result.metadata.is_cached = is_cached
    return result


def get_support_insights(
    db: Session,
    force_refresh: bool = False,
    client: Optional[GeminiClient] = None,
) -> List[str]:
    """Generates customer support intelligence from aggregated metrics only.
    Strictly excludes customer PII, names, emails, and ticket descriptions."""
    ops = get_operations_insights(db, force_refresh=force_refresh, client=client)
    return ops.support_insights


def get_incident_insights(
    db: Session,
    force_refresh: bool = False,
    client: Optional[GeminiClient] = None,
) -> List[str]:
    """Generates operational incident intelligence from severity and system patterns."""
    ops = get_operations_insights(db, force_refresh=force_refresh, client=client)
    return ops.incident_insights


def get_operations_insights(
    db: Session,
    force_refresh: bool = False,
    client: Optional[GeminiClient] = None,
) -> OperationsInsightsResponse:
    """Synthesizes cross-module operational insights across Customer Support and Incident Management.
    Enforces strict PII exclusion and aggregated-data only prompt payloads."""
    cache_key = "intelligence:org:operations"

    if force_refresh:
        allowed, remaining = intelligence_cache.check_refresh_throttle(cache_key)
        if not allowed:
            cached = intelligence_cache.get(cache_key)
            if cached:
                return cached

    def _evaluator() -> OperationsInsightsResponse:
        # 1. Customer Support Aggregation
        db_tickets = db.query(SupportTicket).all()
        categories = (
            db.query(SupportCategory.name, func.count(SupportTicket.id))
            .join(SupportTicket, SupportTicket.category_id == SupportCategory.id)
            .group_by(SupportCategory.name)
            .all()
        )
        cat_dicts = [{"category_name": name, "ticket_count": count} for name, count in categories]

        if db_tickets:
            sup_total = len(db_tickets)
            sup_open = sum(1 for t in db_tickets if t.status in ["open", "assigned"])
            sup_in_prog = sum(1 for t in db_tickets if t.status == "in_progress")
            sup_resolved = sum(1 for t in db_tickets if t.status in ["resolved", "closed"])
            sup_escalated = sum(1 for t in db_tickets if t.status == "escalated")
        elif hasattr(cs_service, "dev_store") and cs_service.dev_store.tickets:
            dev_t = cs_service.dev_store.tickets
            sup_total = len(dev_t)
            sup_open = sum(1 for t in dev_t if t.get("status") in ["open", "assigned"])
            sup_in_prog = sum(1 for t in dev_t if t.get("status") == "in_progress")
            sup_resolved = sum(1 for t in dev_t if t.get("status") in ["resolved", "closed"])
            sup_escalated = sum(1 for t in dev_t if t.get("status") == "escalated")
        else:
            sup_total = sup_open = sup_in_prog = sup_resolved = sup_escalated = 0

        # 2. Incident Aggregation
        inc_total = db.query(Incident).count()
        inc_open = db.query(Incident).filter(Incident.status == "open").count()
        inc_investigating = db.query(Incident).filter(Incident.status == "investigating").count()
        inc_resolved = db.query(Incident).filter(Incident.status == "resolved").count()
        inc_closed = db.query(Incident).filter(Incident.status == "closed").count()

        sev_counts = {
            "critical": db.query(Incident).filter(Incident.severity == "critical").count(),
            "high": db.query(Incident).filter(Incident.severity == "high").count(),
            "medium": db.query(Incident).filter(Incident.severity == "medium").count(),
            "low": db.query(Incident).filter(Incident.severity == "low").count(),
        }

        system_counts = (
            db.query(Incident.affected_system, func.count(Incident.id))
            .filter(Incident.affected_system.isnot(None))
            .group_by(Incident.affected_system)
            .order_by(func.count(Incident.id).desc())
            .limit(5)
            .all()
        )
        sys_dict = {name: count for name, count in system_counts if name}

        # Resolution time
        res_rows = (
            db.query(Incident.created_at, Incident.resolved_at)
            .filter(Incident.resolved_at.isnot(None))
            .all()
        )
        avg_res_min: Optional[float] = None
        if res_rows:
            tot_sec = sum(
                ((r.resolved_at.replace(tzinfo=None) if r.resolved_at else None) -
                 (r.created_at.replace(tzinfo=None) if r.created_at else None)).total_seconds()
                for r in res_rows if r.resolved_at and r.created_at
            )
            avg_res_min = round(tot_sec / 60.0 / len(res_rows), 1)

        # 3. Deterministic rule-based insights
        support_insights: List[str] = []
        if sup_total > 0:
            support_insights.append(
                f"Customer Support has {sup_total} total tickets with {sup_open} open and {sup_escalated} escalated."
            )
            if cat_dicts:
                top_cat = sorted(cat_dicts, key=lambda x: x["ticket_count"], reverse=True)[0]
                support_insights.append(
                    f"Primary customer friction category is '{top_cat['category_name']}' with {top_cat['ticket_count']} tickets."
                )
        else:
            support_insights.append("Support ticket queue is clear with 0 active tickets.")

        incident_insights: List[str] = []
        if inc_total > 0:
            incident_insights.append(
                f"Recorded {inc_total} incidents ({inc_open + inc_investigating} active, "
                f"{sev_counts['critical']} critical, {sev_counts['high']} high)."
            )
            if sys_dict:
                top_sys = list(sys_dict.items())[0]
                incident_insights.append(
                    f"Primary affected system is '{top_sys[0]}' with {top_sys[1]} recorded incident(s)."
                )
            if avg_res_min:
                incident_insights.append(f"Average incident resolution time is {avg_res_min} minutes.")
        else:
            incident_insights.append("Zero production incidents recorded; infrastructure status healthy.")

        operational_summary = (
            f"Operations summary: {sup_open} open customer tickets, {inc_open + inc_investigating} active incidents. "
            f"Overall operational stability remains within standard parameters."
        )

        ai_client = client or GeminiClient()
        is_gemini_active = ai_client.is_configured

        if is_gemini_active and (sup_total > 0 or inc_total > 0):
            # Minimized & anonymized metrics prompt
            sanitized_sup = sanitize_support_data_for_ai(
                sup_total, sup_open, sup_in_prog, sup_resolved, sup_escalated, cat_dicts
            )
            sanitized_inc = sanitize_incident_data_for_ai(
                inc_total, inc_open, inc_investigating, inc_resolved, inc_closed,
                sev_counts, sys_dict, avg_res_min
            )

            prompt = (
                f"You are an enterprise operations intelligence analyst.\n"
                f"Analyze the following aggregated operational metrics:\n"
                f"Customer Support: {sanitized_sup}\n"
                f"Incident Management: {sanitized_inc}\n\n"
                f"Instructions:\n"
                f"1. Generate 1-3 support insights highlighting customer friction points.\n"
                f"2. Generate 1-3 incident insights highlighting recurring system vulnerabilities.\n"
                f"3. Provide a concise 2-sentence executive operational summary.\n"
                f"4. Do NOT reference individual people, customers, or internal employee identifiers."
            )
            try:
                payload = ai_client.generate_structured(prompt, _GeminiOperationsPayload)
                support_insights = payload.support_insights or support_insights
                incident_insights = payload.incident_insights or incident_insights
                operational_summary = payload.operational_summary or operational_summary
            except Exception as exc:  # noqa: BLE001
                logger.warning("Gemini operations analysis failed: %s. Using rule fallback.", exc)

        metadata = AIMetadata(
            model_provider="gemini" if is_gemini_active else "deterministic_rule_engine",
            model_name=ai_client.model_name if is_gemini_active else "rule_engine_v1",
            is_fallback=not is_gemini_active,
        )

        return OperationsInsightsResponse(
            support_insights=support_insights,
            incident_insights=incident_insights,
            operational_summary=operational_summary,
            metadata=metadata,
        )

    result, is_cached = intelligence_cache.get_or_evaluate(
        key=cache_key,
        evaluator_fn=_evaluator,
        ttl=DEFAULT_TTL_SECONDS,
        force_refresh=force_refresh,
    )
    result.metadata.is_cached = is_cached
    return result


def get_executive_recommendations(
    db: Session,
    project_id: Optional[int] = None,
    force_refresh: bool = False,
    client: Optional[GeminiClient] = None,
) -> ExecutiveSummaryResponse:
    """Synthesizes cross-module intelligence into four-part executive recommendations:
      1. Observation
      2. Why This Matters
      3. Possible Future Consequence
      4. Recommended Preventive Action

    All recommendations are grounded in verified metrics and are strictly advisory."""
    cache_key = (
        f"intelligence:project:{project_id}:executive_recommendations"
        if project_id is not None
        else "intelligence:org:executive_recommendations"
    )

    if force_refresh:
        allowed, remaining = intelligence_cache.check_refresh_throttle(cache_key)
        if not allowed:
            cached = intelligence_cache.get(cache_key)
            if cached:
                return cached

    def _evaluator() -> ExecutiveSummaryResponse:
        # Gather underlying intelligence
        project_risks = get_project_risk_insights(db, project_id=project_id, client=client)
        sprint_delays = get_sprint_delay_insights(db, project_id=project_id, client=client)
        workloads = get_workload_bottleneck_insights(db, project_id=project_id, client=client)
        operations = get_operations_insights(db, client=client)

        high_risk_projects = [p for p in project_risks.projects if p.deterministic_risk_level == RiskLevel.HIGH]
        delayed_sprints = [s for s in sprint_delays.sprints if s.delay_status == DelayStatus.DELAYED]
        severe_bottlenecks = [b for b in workloads.bottlenecks if b.bottleneck_severity == BottleneckSeverity.HIGH]

        # Determine overall status deterministically
        if high_risk_projects or delayed_sprints or severe_bottlenecks:
            overall_status = "critical_attention"
        elif any(p.deterministic_risk_level == RiskLevel.MEDIUM for p in project_risks.projects):
            overall_status = "attention_required"
        else:
            overall_status = "healthy"

        # Deterministic recommendations
        recommendations: List[ExecutiveRecommendationItem] = []

        # 1. Project Risk Recommendation
        for p in high_risk_projects[:2]:
            recommendations.append(
                ExecutiveRecommendationItem(
                    id=f"rec-proj-{p.project_id}",
                    category=RecommendationCategory.PROJECT,
                    title=f"Delivery Risk Escalation: {p.project_name}",
                    observation=p.risk_explanation,
                    why_it_matters=f"Project is evaluated at HIGH risk ({p.deterministic_risk_score}/100) based on verified overdue deliverables.",
                    potential_consequence=p.potential_consequences,
                    recommended_preventive_action=p.recommended_actions[0] if p.recommended_actions else "Reallocate workload and review sprint milestones.",
                    urgency=UrgencyLevel.HIGH,
                    requires_human_approval=True,
                )
            )

        # 2. Sprint Delay Recommendation
        for s in delayed_sprints[:2]:
            recommendations.append(
                ExecutiveRecommendationItem(
                    id=f"rec-sprint-{s.sprint_id}",
                    category=RecommendationCategory.PROJECT,
                    title=f"Sprint Deadline Slippage: {s.sprint_name}",
                    observation=s.delay_explanation,
                    why_it_matters="Incomplete sprints jeopardize dependent product roadmaps and downstream customer commitments.",
                    potential_consequence="Workload spillover will compress subsequent sprint capacity.",
                    recommended_preventive_action=s.recommended_mitigations[0] if s.recommended_mitigations else "Prioritize unblocking overdue tasks.",
                    urgency=UrgencyLevel.HIGH,
                    requires_human_approval=True,
                )
            )

        # 3. Workload Bottleneck Recommendation
        for b in severe_bottlenecks[:1]:
            recommendations.append(
                ExecutiveRecommendationItem(
                    id=f"rec-workload-{b.team_or_project.lower().replace(' ', '-')}",
                    category=RecommendationCategory.WORKLOAD,
                    title=f"Engineering Bottleneck in {b.team_or_project}",
                    observation=b.observation,
                    why_it_matters="Workload concentration creates delivery single-points-of-failure and team fatigue.",
                    potential_consequence="Increased bug rates and critical task delays due to overextended engineers.",
                    recommended_preventive_action=b.suggested_balancing_action,
                    urgency=UrgencyLevel.MEDIUM,
                    requires_human_approval=True,
                )
            )

        # 4. Default healthy recommendation if queue is clean
        if not recommendations:
            recommendations.append(
                ExecutiveRecommendationItem(
                    id="rec-healthy-general",
                    category=RecommendationCategory.OPERATIONS,
                    title="Operations and Delivery Cadence Stable",
                    observation="All active projects, sprints, and workload allocations are within healthy parameters.",
                    why_it_matters="Predictable delivery cadence enables reliable enterprise planning and release scheduling.",
                    potential_consequence="Premature scope expansion without capacity review could disrupt balance.",
                    recommended_preventive_action="Maintain weekly sprint review rhythm and monitor backlog growth.",
                    urgency=UrgencyLevel.LOW,
                    requires_human_approval=True,
                )
            )

        exec_brief = (
            f"Enterprise AI Intelligence Assessment: Overall organization posture is '{overall_status}'. "
            f"Identified {len(high_risk_projects)} high-risk project(s), {len(delayed_sprints)} delayed sprint(s), "
            f"and {len(severe_bottlenecks)} high-severity workload bottlenecks across active teams."
        )

        ai_client = client or GeminiClient()
        is_gemini_active = ai_client.is_configured

        # Attempt Gemini enhancement if configured
        if is_gemini_active:
            prompt = (
                f"You are an executive enterprise intelligence advisor.\n"
                f"Synthesize the following organizational posture:\n"
                f"Overall Posture: {overall_status.upper()}\n"
                f"High-Risk Projects: {len(high_risk_projects)}\n"
                f"Delayed Sprints: {len(delayed_sprints)}\n"
                f"Workload Bottlenecks: {len(severe_bottlenecks)}\n"
                f"Operations Summary: {operations.operational_summary}\n\n"
                f"Instructions:\n"
                f"1. Generate a 2-3 sentence executive brief summarizing enterprise health.\n"
                f"2. Provide 2-4 structured recommendations strictly using the 4-part structure:\n"
                f"   (observation, why_it_matters, potential_consequence, recommended_preventive_action).\n"
                f"3. All recommendations must be grounded strictly in these verified metrics.\n"
                f"4. Do not include personal names or confidential PII."
            )
            try:
                gemini_resp = ai_client.generate_structured(prompt, ExecutiveSummaryResponse)
                # Ensure advisory and approval constraints are strictly preserved
                for rec in gemini_resp.recommendations:
                    rec.requires_human_approval = True
                exec_brief = gemini_resp.executive_brief
                recommendations = gemini_resp.recommendations or recommendations
                overall_status = gemini_resp.overall_status or overall_status
            except Exception as exc:  # noqa: BLE001
                logger.warning("Gemini executive brief synthesis failed: %s. Using rule fallback.", exc)

        metadata = AIMetadata(
            model_provider="gemini" if is_gemini_active else "deterministic_rule_engine",
            model_name=ai_client.model_name if is_gemini_active else "rule_engine_v1",
            is_fallback=not is_gemini_active,
        )

        return ExecutiveSummaryResponse(
            overall_status=overall_status,
            executive_brief=exec_brief,
            recommendations=recommendations,
            metadata=metadata,
        )

    result, is_cached = intelligence_cache.get_or_evaluate(
        key=cache_key,
        evaluator_fn=_evaluator,
        ttl=DEFAULT_TTL_SECONDS,
        force_refresh=force_refresh,
    )
    result.metadata.is_cached = is_cached
    return result
