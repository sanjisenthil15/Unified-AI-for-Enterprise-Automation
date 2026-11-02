"""
core/permissions.py

Centralized permission constants and role-to-permission mappings for the
RBAC system.  Every module-level authorization check should reference
these constants instead of hard-coding role name strings, so permission
changes only need to happen in one place.

Usage in a router:
    from core.permissions import RECRUITMENT_MANAGE_ROLES
    current_user: User = Depends(require_roles(RECRUITMENT_MANAGE_ROLES))
"""

# ------------------------------------------------------------------ #
# Role name constants
# ------------------------------------------------------------------ #

ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_HR = "hr_manager"
ROLE_TEAM_LEAD = "team_lead"        # not a DB role — project-relational
ROLE_EMPLOYEE = "employee"
ROLE_SUPPORT_AGENT = "support_agent"
ROLE_RECRUITER = "recruiter"
ROLE_VIEWER = "viewer"
ROLE_CUSTOMER = "customer"

# ------------------------------------------------------------------ #
# Roles that bypass project-level authorization checks
# (admin, hr_manager, and now manager). Used by core/authorization.py.
# ------------------------------------------------------------------ #

OVERRIDE_ROLES = (ROLE_ADMIN, ROLE_HR, ROLE_MANAGER)

# ------------------------------------------------------------------ #
# Module-level role lists — used with require_roles()
# ------------------------------------------------------------------ #

# Recruitment — who can manage job postings, resumes, AI analysis
RECRUITMENT_MANAGE_ROLES = [ROLE_ADMIN, ROLE_HR, ROLE_RECRUITER]

# Recruitment — who can view candidate data (resumes, scores, PII)
RECRUITMENT_VIEW_CANDIDATES_ROLES = [ROLE_ADMIN, ROLE_HR, ROLE_RECRUITER]

# Customer Support — who can manage knowledge base, categories, teams
SUPPORT_MANAGE_ROLES = [ROLE_ADMIN, ROLE_SUPPORT_AGENT]

# Customer Support — who has unrestricted ticket access (all tickets)
SUPPORT_FULL_ACCESS_ROLES = [ROLE_ADMIN, ROLE_SUPPORT_AGENT]

# Sprints — who can view cross-project overview and manage sprints organization-wide
SPRINT_MANAGE_ROLES = [ROLE_ADMIN, ROLE_HR, ROLE_MANAGER]

# Incident Management — who can create, update, resolve incidents
INCIDENT_WRITE_ROLES = [ROLE_ADMIN, ROLE_SUPPORT_AGENT, ROLE_MANAGER]

# Incident Management — who can assign and delete incidents
INCIDENT_ASSIGN_ROLES = [ROLE_ADMIN, ROLE_SUPPORT_AGENT, ROLE_MANAGER]

# Incident Management — who can report (create) an incident
# (broader than write — any authenticated employee should be able to report)
INCIDENT_REPORT_ROLES = [
    ROLE_ADMIN, ROLE_MANAGER, ROLE_HR, ROLE_SUPPORT_AGENT,
    ROLE_RECRUITER, ROLE_EMPLOYEE,
]

# Employee Management — who can view the full employee directory
EMPLOYEE_VIEW_ROLES = [ROLE_ADMIN, ROLE_HR, ROLE_MANAGER]

# Employee Management — who can onboard/edit employees
EMPLOYEE_MANAGE_ROLES = [ROLE_ADMIN, ROLE_HR]

# Analytics — who can view organization-wide executive analytics
ANALYTICS_ORG_ROLES = [ROLE_ADMIN, ROLE_MANAGER]

# Analytics — read-only aggregate views (overview, project performance,
# operations, trends) also open to Viewer. Never the workforce endpoint:
# it lists named employees' task / overdue counts.
ANALYTICS_AGGREGATE_READ_ROLES = [ROLE_ADMIN, ROLE_MANAGER, ROLE_VIEWER]

# Analytics — who can view general analytics (Team Leads access project-scoped via authorization helper)
ANALYTICS_VIEW_ROLES = [ROLE_ADMIN, ROLE_MANAGER, ROLE_HR]

# Account Security — administrative password reset.
# Requester role -> target roles it may reset. Anything not listed is
# forbidden: HR may only reset ordinary employees (resetting a manager,
# admin or another HR account would let HR sign in as them), nobody may
# reset an admin, and self-reset is rejected separately (use change-password).
PASSWORD_RESET_REQUESTER_ROLES = [ROLE_ADMIN, ROLE_HR]
PASSWORD_RESET_TARGETS = {
    ROLE_ADMIN: {ROLE_EMPLOYEE, ROLE_HR, ROLE_MANAGER, ROLE_SUPPORT_AGENT, ROLE_RECRUITER, ROLE_VIEWER},
    ROLE_HR: {ROLE_EMPLOYEE},
}

