"""Tests for Project Team Visibility (Feature 1).

Verifies that:
- Staffed employees can view their assigned project's members.
- Employees cannot view members of projects they are not assigned to (403 Forbidden).
- Assigned project managers and team leads can view project members.
- Unassigned managers cannot view project members (403 Forbidden).
- Admin and HR Manager retain global visibility.
- Member details include circular photo_url, full_name, email, job_title, team_role, department_name.
"""
import uuid
from datetime import date
from models.user import User
from models.project import Project
from models.employee import Employee
from models.department import Department


BASE = "/api/v1/employee-management"


def test_project_members_visibility_and_rbac(client, db, new_user):
    tag = uuid.uuid4().hex[:8]
    admin = new_user("Admin User", role="admin")
    hr_mgr = new_user("HR Manager", role="hr_manager")
    mgr_assigned = new_user("Assigned Manager", role="manager")
    mgr_other = new_user("Other Manager", role="manager")
    emp_staffed = new_user("Staffed Employee", role="employee")
    emp_other = new_user("Other Employee", role="employee")

    # Create two projects with unique names
    p1 = Project(name=f"Project Alpha {tag}", status="active", start_date=date(2026, 1, 1), manager_user_id=mgr_assigned["id"])
    p2 = Project(name=f"Project Beta {tag}", status="active", start_date=date(2026, 1, 1), manager_user_id=mgr_other["id"])
    db.add_all([p1, p2])
    db.commit()
    db.refresh(p1)
    db.refresh(p2)

    # Department
    dept = Department(name=f"Engineering {tag}")
    db.add(dept)
    db.commit()
    db.refresh(dept)

    # Create Employee record for emp_staffed attached to p1
    e1 = Employee(
        user_id=emp_staffed["id"],
        department_id=dept.id,
        project_id=p1.id,
        job_title="Senior Frontend Engineer",
        employee_code="EMP-101",
        hire_date=date(2026, 1, 1),
        employment_type="full_time",
        status="active",
    )
    # Create Employee record for emp_other attached to p2
    e2 = Employee(
        user_id=emp_other["id"],
        department_id=dept.id,
        project_id=p2.id,
        job_title="Backend Engineer",
        employee_code="EMP-102",
        hire_date=date(2026, 1, 1),
        employment_type="full_time",
        status="active",
    )
    db.add_all([e1, e2])
    db.commit()
    db.refresh(e1)
    db.refresh(e2)

    # Designate e1 as team lead for p1
    p1.team_lead_id = e1.id
    db.commit()

    # 1. Staffed employee accesses their project members -> 200 OK
    r = client.get(f"{BASE}/projects/{p1.id}/members", headers=emp_staffed["headers"])
    assert r.status_code == 200, r.text
    members = r.json()
    assert len(members) == 1
    m = members[0]
    assert m["id"] == e1.id
    assert m["full_name"] == "Staffed Employee"
    assert m["email"] == emp_staffed["email"]
    assert m["job_title"] == "Senior Frontend Engineer"
    assert m["team_role"] == "Team Lead"
    assert m["department_name"] == f"Engineering {tag}"
    assert "photo_url" in m

    # 2. Staffed employee accessing other project -> 403 Forbidden
    r_unauth = client.get(f"{BASE}/projects/{p2.id}/members", headers=emp_staffed["headers"])
    assert r_unauth.status_code == 403

    # 3. Assigned manager accesses p1 members -> 200 OK
    r_mgr = client.get(f"{BASE}/projects/{p1.id}/members", headers=mgr_assigned["headers"])
    assert r_mgr.status_code == 200

    # 4. Assigned manager accessing unassigned project p2 -> 403 Forbidden
    r_mgr_other = client.get(f"{BASE}/projects/{p2.id}/members", headers=mgr_assigned["headers"])
    assert r_mgr_other.status_code == 403

    # 5. Admin accesses p1 and p2 members -> 200 OK
    assert client.get(f"{BASE}/projects/{p1.id}/members", headers=admin["headers"]).status_code == 200
    assert client.get(f"{BASE}/projects/{p2.id}/members", headers=admin["headers"]).status_code == 200

    # 6. HR Manager accesses p1 and p2 members -> 200 OK
    assert client.get(f"{BASE}/projects/{p1.id}/members", headers=hr_mgr["headers"]).status_code == 200
    assert client.get(f"{BASE}/projects/{p2.id}/members", headers=hr_mgr["headers"]).status_code == 200

    # 7. Unauthenticated request -> 401 Unauthorized
    assert client.get(f"{BASE}/projects/{p1.id}/members").status_code == 401
