"""
modules/analytics/schemas.py

Pydantic schemas for the Centralized Analytics Dashboard module.
Serves executive summaries, project-level performance, workforce allocations,
cross-module operational metrics, and trend datasets for Recharts.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# 1. Executive Overview Schemas
# --------------------------------------------------------------------------- #

class AnalyticsOverviewResponse(BaseModel):
    """Organization-wide executive KPI summary."""
    total_employees: int
    active_employees: int
    total_projects: int
    active_projects: int
    total_tasks: int
    completed_tasks: int
    overall_task_completion_rate: float = Field(..., description="Value between 0.0 and 100.0")
    open_incidents: int
    open_support_tickets: int
    active_job_postings: int
    total_resumes: int
    total_meetings: int
    meeting_action_items_count: int
    action_items_converted_count: int
    action_items_conversion_rate: float = Field(..., description="Value between 0.0 and 100.0")


# --------------------------------------------------------------------------- #
# 2. Project Performance Schemas
# --------------------------------------------------------------------------- #

class ProjectAnalyticsItem(BaseModel):
    """Detailed performance and task metrics for a single project."""
    project_id: int
    project_name: str
    team_lead_name: Optional[str] = None
    member_count: int
    active_sprint_name: Optional[str] = None
    tasks_total: int
    tasks_done: int
    tasks_in_progress: int
    tasks_todo: int
    tasks_blocked: int
    tasks_overdue: int
    completion_rate: float = Field(..., description="Percentage between 0.0 and 100.0")
    health_status: str = Field(..., description="'healthy', 'at_risk', or 'critical'")


class ProjectAnalyticsResponse(BaseModel):
    """List of project performance summaries."""
    projects: List[ProjectAnalyticsItem]
    total_projects: int


# --------------------------------------------------------------------------- #
# 3. Workforce & Allocation Schemas
# --------------------------------------------------------------------------- #

class WorkforceDepartmentItem(BaseModel):
    department_id: Optional[int] = None
    department_name: str
    employee_count: int


class WorkforceProjectAllocationItem(BaseModel):
    project_id: Optional[int] = None
    project_name: str
    headcount: int


class WorkforceWorkloadItem(BaseModel):
    employee_id: int
    employee_name: str
    project_name: Optional[str] = None
    tasks_assigned: int
    tasks_completed: int
    tasks_pending: int
    tasks_overdue: int


class WorkforceAttendanceSummary(BaseModel):
    total_records: int
    present_count: int
    late_count: int
    on_leave_count: int
    absent_count: int
    average_checkin_rate: float = Field(..., description="Average rate between 0.0 and 1.0")


class WorkforceAnalyticsResponse(BaseModel):
    total_workforce: int
    active_workforce: int
    department_distribution: List[WorkforceDepartmentItem]
    project_allocations: List[WorkforceProjectAllocationItem]
    workload_distribution: List[WorkforceWorkloadItem]
    attendance_summary: WorkforceAttendanceSummary


# --------------------------------------------------------------------------- #
# 4. Operations & Cross-Module Schemas
# --------------------------------------------------------------------------- #

class IncidentAnalyticsSummary(BaseModel):
    total: int
    open: int
    investigating: int
    resolved: int
    closed: int
    severity_breakdown: Dict[str, int]
    avg_resolution_minutes: Optional[float] = None


class SupportCategoryDistributionItem(BaseModel):
    category_id: Optional[int] = None
    category_name: str
    ticket_count: int


class SupportAnalyticsSummary(BaseModel):
    total_tickets: int
    open_tickets: int
    in_progress_tickets: int
    resolved_tickets: int
    escalated_tickets: int
    category_distribution: List[SupportCategoryDistributionItem]


class RecruitmentAnalyticsSummary(BaseModel):
    open_positions: int
    total_applications: int
    shortlisted: int
    rejected: int
    waiting: int


class MeetingAnalyticsSummary(BaseModel):
    total_meetings: int
    total_duration_minutes: int
    avg_duration_minutes: float
    action_items_total: int
    action_items_completed: int
    action_items_converted_to_sprint: int
    conversion_rate: float = Field(..., description="Percentage between 0.0 and 100.0")


class OperationsAnalyticsResponse(BaseModel):
    incidents: IncidentAnalyticsSummary
    support: SupportAnalyticsSummary
    recruitment: RecruitmentAnalyticsSummary
    meetings: MeetingAnalyticsSummary


# --------------------------------------------------------------------------- #
# 5. Trend Time-Series Schemas
# --------------------------------------------------------------------------- #

class DailyTrendItem(BaseModel):
    date: str
    tasks_completed: int = 0
    tasks_created: int = 0
    tickets_created: int = 0
    tickets_resolved: int = 0
    incidents_reported: int = 0


class AnalyticsTrendsResponse(BaseModel):
    daily_trends: List[DailyTrendItem]
    range_days: int
