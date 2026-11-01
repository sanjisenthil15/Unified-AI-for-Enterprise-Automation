"""
modules/analytics/service.py

Business logic for the Centralized Analytics Dashboard.
Aggregates cross-module metrics, computes project performance health,
summarizes workforce allocations, and prepares Recharts-ready trend datasets.

Design Guidelines:
  - Use SQL-level aggregations (func.count, func.sum) rather than fetching whole tables.
  - Zero-division safe: always returns 0.0 instead of throwing ZeroDivisionError.
  - Graceful empty states: modules with 0 rows return structured 0-valued responses.
  - No invasive employee surveillance or unsupported productivity scores.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional
from sqlalchemy import func, case
from sqlalchemy.orm import Session, joinedload

from models.attendance import Attendance
from models.department import Department
from models.employee import Employee
from models.incident import Incident
from models.job_posting import JobPosting
from models.meeting import Meeting
from models.meeting_action_item import MeetingActionItem
from models.project import Project
from models.resume import Resume
from models.sprint import Sprint
from models.sprint_task import SprintTask
from models.ticket import SupportCategory, SupportTicket
from models.user import User

from modules.customer_support import service as cs_service
from modules.attendance.service import compute_checkin_rates_for_employees
from modules.analytics.schemas import (
    AnalyticsOverviewResponse,
    AnalyticsTrendsResponse,
    DailyTrendItem,
    IncidentAnalyticsSummary,
    MeetingAnalyticsSummary,
    OperationsAnalyticsResponse,
    ProjectAnalyticsItem,
    ProjectAnalyticsResponse,
    RecruitmentAnalyticsSummary,
    SupportAnalyticsSummary,
    SupportCategoryDistributionItem,
    WorkforceAnalyticsResponse,
    WorkforceAttendanceSummary,
    WorkforceDepartmentItem,
    WorkforceProjectAllocationItem,
    WorkforceWorkloadItem,
)


# --------------------------------------------------------------------------- #
# 1. Organization Overview
# --------------------------------------------------------------------------- #

def get_analytics_overview(db: Session) -> AnalyticsOverviewResponse:
    """Computes organization-wide executive KPIs across all active modules."""

    total_employees = (
        db.query(Employee)
        .filter(Employee.deleted_at.is_(None))
        .count()
    )
    active_employees = (
        db.query(Employee)
        .filter(Employee.deleted_at.is_(None), Employee.status == "active")
        .count()
    )

    total_projects = db.query(Project).count()
    active_projects = (
        db.query(Sprint.project_id)
        .filter(Sprint.status == "active")
        .distinct()
        .count()
    )
    if active_projects == 0 and total_projects > 0:
        # Fallback to projects that have staffed members
        active_projects = (
            db.query(Employee.project_id)
            .filter(Employee.deleted_at.is_(None), Employee.project_id.isnot(None))
            .distinct()
            .count()
        )

    total_tasks = db.query(SprintTask).count()
    completed_tasks = (
        db.query(SprintTask)
        .filter(SprintTask.status == "done")
        .count()
    )
    task_completion_rate = (
        round((completed_tasks / total_tasks) * 100.0, 1) if total_tasks > 0 else 0.0
    )

    open_incidents = (
        db.query(Incident)
        .filter(Incident.status.in_(["open", "investigating"]))
        .count()
    )

    # Support tickets: check DB first, fallback to dev_store if DB has 0 rows
    db_open_tickets = (
        db.query(SupportTicket)
        .filter(SupportTicket.status.in_(["open", "in_progress"]))
        .count()
    )
    if (
        db_open_tickets == 0
        and hasattr(cs_service, "dev_store")
        and cs_service.dev_store.tickets
    ):
        open_support_tickets = sum(
            1
            for t in cs_service.dev_store.tickets
            if t.get("status") in ["open", "assigned", "in_progress"]
        )
    else:
        open_support_tickets = db_open_tickets

    active_jobs = (
        db.query(JobPosting)
        .filter(JobPosting.status == "active")
        .count()
    )
    total_resumes = db.query(Resume).count()

    total_meetings = db.query(Meeting).count()
    total_action_items = db.query(MeetingActionItem).count()
    converted_action_items = (
        db.query(MeetingActionItem)
        .filter(MeetingActionItem.converted_sprint_task_id.isnot(None))
        .count()
    )
    action_item_conv_rate = (
        round((converted_action_items / total_action_items) * 100.0, 1)
        if total_action_items > 0
        else 0.0
    )

    return AnalyticsOverviewResponse(
        total_employees=total_employees,
        active_employees=active_employees,
        total_projects=total_projects,
        active_projects=active_projects,
        total_tasks=total_tasks,
        completed_tasks=completed_tasks,
        overall_task_completion_rate=task_completion_rate,
        open_incidents=open_incidents,
        open_support_tickets=open_support_tickets,
        active_job_postings=active_jobs,
        total_resumes=total_resumes,
        total_meetings=total_meetings,
        meeting_action_items_count=total_action_items,
        action_items_converted_count=converted_action_items,
        action_items_conversion_rate=action_item_conv_rate,
    )


# --------------------------------------------------------------------------- #
# 2. Project Performance Analytics
# --------------------------------------------------------------------------- #

def get_project_analytics(
    db: Session,
    project_id: Optional[int] = None,
) -> ProjectAnalyticsResponse:
    """Computes project-by-project task status breakdown, completion rate, and health."""

    projects_query = db.query(Project).options(
        joinedload(Project.team_lead).joinedload(Employee.user),
        joinedload(Project.members),
    )
    if project_id is not None:
        projects_query = projects_query.filter(Project.id == project_id)

    projects = projects_query.order_by(Project.id).all()
    today = date.today()

    items: List[ProjectAnalyticsItem] = []

    for proj in projects:
        # Active sprint name
        active_sprint = (
            db.query(Sprint)
            .filter(Sprint.project_id == proj.id, Sprint.status == "active")
            .order_by(Sprint.end_date.desc())
            .first()
        )
        active_sprint_name = active_sprint.name if active_sprint else None

        # Fetch all tasks linked to this project's sprints
        tasks = (
            db.query(SprintTask)
            .join(Sprint, Sprint.id == SprintTask.sprint_id)
            .filter(Sprint.project_id == proj.id)
            .all()
        )

        tasks_total = len(tasks)
        tasks_done = sum(1 for t in tasks if t.status == "done")
        tasks_in_progress = sum(1 for t in tasks if t.status == "in_progress")
        tasks_todo = sum(1 for t in tasks if t.status == "todo")
        tasks_blocked = sum(1 for t in tasks if t.status == "blocked")
        tasks_overdue = sum(
            1
            for t in tasks
            if t.status != "done" and t.due_date is not None and t.due_date < today
        )

        completion_rate = (
            round((tasks_done / tasks_total) * 100.0, 1) if tasks_total > 0 else 0.0
        )

        # Health evaluation
        if tasks_overdue == 0 and (completion_rate >= 70.0 or tasks_total == 0):
            health = "healthy"
        elif tasks_overdue <= 2 or completion_rate >= 40.0:
            health = "at_risk"
        else:
            health = "critical"

        team_lead_name = (
            proj.team_lead.user.full_name
            if (proj.team_lead and proj.team_lead.user)
            else None
        )

        items.append(
            ProjectAnalyticsItem(
                project_id=proj.id,
                project_name=proj.name,
                team_lead_name=team_lead_name,
                member_count=len(proj.members),
                active_sprint_name=active_sprint_name,
                tasks_total=tasks_total,
                tasks_done=tasks_done,
                tasks_in_progress=tasks_in_progress,
                tasks_todo=tasks_todo,
                tasks_blocked=tasks_blocked,
                tasks_overdue=tasks_overdue,
                completion_rate=completion_rate,
                health_status=health,
            )
        )

    return ProjectAnalyticsResponse(
        projects=items,
        total_projects=len(items),
    )


# --------------------------------------------------------------------------- #
# 3. Workforce & Allocation Analytics
# --------------------------------------------------------------------------- #

def get_workforce_analytics(
    db: Session,
    project_id: Optional[int] = None,
) -> WorkforceAnalyticsResponse:
    """Computes workforce distributions by department and project, workload allocations,
    and high-level attendance summary."""

    emp_query = db.query(Employee).filter(Employee.deleted_at.is_(None))
    if project_id is not None:
        emp_query = emp_query.filter(Employee.project_id == project_id)

    employees = emp_query.options(
        joinedload(Employee.user),
        joinedload(Employee.project),
        joinedload(Employee.department),
    ).order_by(Employee.id).all()

    total_workforce = len(employees)
    active_workforce = sum(1 for e in employees if e.status == "active")

    # Department distribution
    dept_counts: Dict[str, int] = {}
    dept_id_map: Dict[str, Optional[int]] = {}
    for e in employees:
        d_name = e.department.name if e.department else "Unassigned"
        dept_counts[d_name] = dept_counts.get(d_name, 0) + 1
        if e.department and d_name not in dept_id_map:
            dept_id_map[d_name] = e.department.id

    department_distribution = [
        WorkforceDepartmentItem(
            department_id=dept_id_map.get(d_name),
            department_name=d_name,
            employee_count=count,
        )
        for d_name, count in sorted(dept_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    # Project allocation distribution
    proj_counts: Dict[str, int] = {}
    proj_id_map: Dict[str, Optional[int]] = {}
    for e in employees:
        p_name = e.project.name if e.project else "Unassigned"
        proj_counts[p_name] = proj_counts.get(p_name, 0) + 1
        if e.project and p_name not in proj_id_map:
            proj_id_map[p_name] = e.project.id

    project_allocations = [
        WorkforceProjectAllocationItem(
            project_id=proj_id_map.get(p_name),
            project_name=p_name,
            headcount=count,
        )
        for p_name, count in sorted(proj_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    # Workload distribution per employee
    employee_ids = [e.id for e in employees]
    today = date.today()

    workload_items: List[WorkforceWorkloadItem] = []
    if employee_ids:
        # Single batched query for task counts per employee
        tasks = (
            db.query(SprintTask)
            .filter(SprintTask.assignee_id.in_(employee_ids))
            .all()
        )
        tasks_by_emp: Dict[int, List[SprintTask]] = {eid: [] for eid in employee_ids}
        for t in tasks:
            if t.assignee_id in tasks_by_emp:
                tasks_by_emp[t.assignee_id].append(t)

        for e in employees:
            e_tasks = tasks_by_emp.get(e.id, [])
            t_total = len(e_tasks)
            t_done = sum(1 for t in e_tasks if t.status == "done")
            t_pending = sum(1 for t in e_tasks if t.status != "done")
            t_overdue = sum(
                1
                for t in e_tasks
                if t.status != "done" and t.due_date is not None and t.due_date < today
            )

            emp_name = e.user.full_name if e.user else f"Employee {e.id}"
            proj_name = e.project.name if e.project else None

            workload_items.append(
                WorkforceWorkloadItem(
                    employee_id=e.id,
                    employee_name=emp_name,
                    project_name=proj_name,
                    tasks_assigned=t_total,
                    tasks_completed=t_done,
                    tasks_pending=t_pending,
                    tasks_overdue=t_overdue,
                )
            )

    # Attendance summary
    att_query = db.query(Attendance)
    if employee_ids:
        att_query = att_query.filter(Attendance.employee_id.in_(employee_ids))
    att_records = att_query.all()

    total_att = len(att_records)
    present_cnt = sum(1 for a in att_records if a.status == "present")
    late_cnt = sum(1 for a in att_records if a.status == "late")
    leave_cnt = sum(1 for a in att_records if a.status == "on_leave")
    absent_cnt = sum(1 for a in att_records if a.status == "absent")

    # Batched 30-day checkin rate
    avg_rate = 1.0
    if employee_ids and total_att > 0:
        start_date = today - timedelta(days=30)
        rates = compute_checkin_rates_for_employees(db, employee_ids, start_date, today)
        if rates:
            avg_rate = round(sum(rates.values()) / len(rates), 2)

    attendance_summary = WorkforceAttendanceSummary(
        total_records=total_att,
        present_count=present_cnt,
        late_count=late_cnt,
        on_leave_count=leave_cnt,
        absent_count=absent_cnt,
        average_checkin_rate=avg_rate,
    )

    return WorkforceAnalyticsResponse(
        total_workforce=total_workforce,
        active_workforce=active_workforce,
        department_distribution=department_distribution,
        project_allocations=project_allocations,
        workload_distribution=workload_items,
        attendance_summary=attendance_summary,
    )


# --------------------------------------------------------------------------- #
# 4. Cross-Module Operational Analytics
# --------------------------------------------------------------------------- #

def get_operations_analytics(db: Session) -> OperationsAnalyticsResponse:
    """Aggregates metrics for Incident Management, Customer Support,
    Recruitment AI, and Meeting Intelligence."""

    # 1. Incidents
    inc_total = db.query(Incident).count()
    inc_open = db.query(Incident).filter(Incident.status == "open").count()
    inc_investigating = db.query(Incident).filter(Incident.status == "investigating").count()
    inc_resolved = db.query(Incident).filter(Incident.status == "resolved").count()
    inc_closed = db.query(Incident).filter(Incident.status == "closed").count()

    sev_counts = {
        "low": db.query(Incident).filter(Incident.severity == "low").count(),
        "medium": db.query(Incident).filter(Incident.severity == "medium").count(),
        "high": db.query(Incident).filter(Incident.severity == "high").count(),
        "critical": db.query(Incident).filter(Incident.severity == "critical").count(),
    }

    avg_res_min: Optional[float] = None
    res_rows = (
        db.query(Incident.created_at, Incident.resolved_at)
        .filter(Incident.resolved_at.isnot(None))
        .all()
    )
    if res_rows:
        tot_sec = sum(
            (
                (r.resolved_at.replace(tzinfo=None) if r.resolved_at else None)
                - (r.created_at.replace(tzinfo=None) if r.created_at else None)
            ).total_seconds()
            for r in res_rows
            if r.resolved_at and r.created_at
        )
        avg_res_min = round(tot_sec / 60 / len(res_rows), 1)

    incidents_summary = IncidentAnalyticsSummary(
        total=inc_total,
        open=inc_open,
        investigating=inc_investigating,
        resolved=inc_resolved,
        closed=inc_closed,
        severity_breakdown=sev_counts,
        avg_resolution_minutes=avg_res_min,
    )

    # 2. Customer Support
    db_tickets = db.query(SupportTicket).all()
    cat_items: List[SupportCategoryDistributionItem] = []

    if db_tickets:
        sup_total = len(db_tickets)
        sup_open = sum(1 for t in db_tickets if t.status in ["open", "assigned"])
        sup_in_progress = sum(1 for t in db_tickets if t.status == "in_progress")
        sup_resolved = sum(1 for t in db_tickets if t.status in ["resolved", "closed"])
        sup_escalated = sum(1 for t in db_tickets if t.status == "escalated")

        cat_counts = (
            db.query(SupportCategory.id, SupportCategory.name, func.count(SupportTicket.id))
            .join(SupportTicket, SupportTicket.category_id == SupportCategory.id)
            .group_by(SupportCategory.id, SupportCategory.name)
            .all()
        )
        cat_items = [
            SupportCategoryDistributionItem(
                category_id=cid,
                category_name=cname,
                ticket_count=cnt,
            )
            for cid, cname, cnt in cat_counts
        ]
    elif hasattr(cs_service, "dev_store") and cs_service.dev_store.tickets:
        # Fallback to in-memory store if DB has 0 rows
        dev_t = cs_service.dev_store.tickets
        sup_total = len(dev_t)
        sup_open = sum(1 for t in dev_t if t.get("status") in ["open", "assigned"])
        sup_in_progress = sum(1 for t in dev_t if t.get("status") == "in_progress")
        sup_resolved = sum(1 for t in dev_t if t.get("status") in ["resolved", "closed"])
        sup_escalated = sum(1 for t in dev_t if t.get("status") == "escalated")

        cat_dict: Dict[str, int] = {}
        for t in dev_t:
            c_name = t.get("category_name", "General Support")
            cat_dict[c_name] = cat_dict.get(c_name, 0) + 1
        cat_items = [
            SupportCategoryDistributionItem(
                category_id=None,
                category_name=cname,
                ticket_count=cnt,
            )
            for cname, cnt in cat_dict.items()
        ]
    else:
        sup_total = sup_open = sup_in_progress = sup_resolved = sup_escalated = 0

    support_summary = SupportAnalyticsSummary(
        total_tickets=sup_total,
        open_tickets=sup_open,
        in_progress_tickets=sup_in_progress,
        resolved_tickets=sup_resolved,
        escalated_tickets=sup_escalated,
        category_distribution=cat_items,
    )

    # 3. Recruitment
    open_jobs = db.query(JobPosting).filter(JobPosting.status == "active").count()
    resumes_total = db.query(Resume).count()
    waiting_resumes = db.query(Resume).filter(Resume.status == "extracted").count()
    shortlisted_resumes = db.query(Resume).filter(Resume.recommendation == "selected").count()
    rejected_resumes = db.query(Resume).filter(Resume.recommendation == "rejected").count()

    recruitment_summary = RecruitmentAnalyticsSummary(
        open_positions=open_jobs,
        total_applications=resumes_total,
        shortlisted=shortlisted_resumes,
        rejected=rejected_resumes,
        waiting=waiting_resumes,
    )

    # 4. Meetings
    total_meetings = db.query(Meeting).count()
    total_dur_sec = (
        db.query(func.coalesce(func.sum(Meeting.duration_sec), 0)).scalar() or 0
    )
    total_dur_min = int(total_dur_sec // 60)
    avg_dur_min = round(total_dur_min / total_meetings, 1) if total_meetings > 0 else 0.0

    action_items_total = db.query(MeetingActionItem).count()
    action_items_completed = (
        db.query(MeetingActionItem)
        .filter(MeetingActionItem.status == "completed")
        .count()
    )
    action_items_converted = (
        db.query(MeetingActionItem)
        .filter(MeetingActionItem.converted_sprint_task_id.isnot(None))
        .count()
    )
    conv_rate = (
        round((action_items_converted / action_items_total) * 100.0, 1)
        if action_items_total > 0
        else 0.0
    )

    meeting_summary = MeetingAnalyticsSummary(
        total_meetings=total_meetings,
        total_duration_minutes=total_dur_min,
        avg_duration_minutes=avg_dur_min,
        action_items_total=action_items_total,
        action_items_completed=action_items_completed,
        action_items_converted_to_sprint=action_items_converted,
        conversion_rate=conv_rate,
    )

    return OperationsAnalyticsResponse(
        incidents=incidents_summary,
        support=support_summary,
        recruitment=recruitment_summary,
        meetings=meeting_summary,
    )


# --------------------------------------------------------------------------- #
# 5. Trend Time-Series Analytics
# --------------------------------------------------------------------------- #

def get_analytics_trends(
    db: Session,
    range_days: int = 14,
    project_id: Optional[int] = None,
) -> AnalyticsTrendsResponse:
    """Prepares chronological daily datapoints for Recharts consumption."""

    today = date.today()
    start_date = today - timedelta(days=range_days - 1)

    # Initialize calendar dictionary
    daily_map: Dict[str, DailyTrendItem] = {}
    current = start_date
    while current <= today:
        d_str = current.isoformat()
        daily_map[d_str] = DailyTrendItem(date=d_str)
        current += timedelta(days=1)

    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)

    # Task trends
    task_q = db.query(SprintTask)
    if project_id is not None:
        task_q = task_q.join(Sprint, Sprint.id == SprintTask.sprint_id).filter(Sprint.project_id == project_id)

    tasks = task_q.filter(SprintTask.created_at >= start_dt).all()
    for t in tasks:
        if t.created_at:
            c_date = t.created_at.date().isoformat()
            if c_date in daily_map:
                daily_map[c_date].tasks_created += 1

        if t.status == "done" and t.updated_at:
            u_date = t.updated_at.date().isoformat()
            if u_date in daily_map:
                daily_map[u_date].tasks_completed += 1

    # Incidents trends (org-wide only if project_id is None)
    if project_id is None:
        incidents = (
            db.query(Incident)
            .filter(Incident.created_at >= start_dt)
            .all()
        )
        for inc in incidents:
            if inc.created_at:
                i_date = inc.created_at.date().isoformat()
                if i_date in daily_map:
                    daily_map[i_date].incidents_reported += 1

        # Support ticket trends
        tickets = (
            db.query(SupportTicket)
            .filter(SupportTicket.created_at >= start_dt)
            .all()
        )
        for tick in tickets:
            if tick.created_at:
                t_date = tick.created_at.date().isoformat()
                if t_date in daily_map:
                    daily_map[t_date].tickets_created += 1
            if tick.resolved_at and tick.status in ["resolved", "closed"]:
                r_date = tick.resolved_at.date().isoformat()
                if r_date in daily_map:
                    daily_map[r_date].tickets_resolved += 1

    sorted_trends = [daily_map[k] for k in sorted(daily_map.keys())]

    return AnalyticsTrendsResponse(
        daily_trends=sorted_trends,
        range_days=range_days,
    )
