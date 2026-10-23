"""Employee Management module — onboarding, directory, self-service profile."""

BASE = "/api/v1/employee-management"


def _role_id(client, headers, name):
    roles = client.get("/api/v1/auth/roles", headers=headers).json()
    return next(r["id"] for r in roles if r["name"] == name)


def test_create_employee_onboards_a_working_login(client, new_user, unique_email):
    admin = new_user("Admin User")  # new_user defaults to role="admin"
    role_id = _role_id(client, admin["headers"], "employee")

    r = client.post(f"{BASE}/employees", headers=admin["headers"], json={
        "full_name": "New Hire",
        "email": unique_email,
        "role_id": role_id,
        "job_title": "Software Engineer",
        "hire_date": "2026-01-15",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["employee"]["job_title"] == "Software Engineer"
    assert body["employee"]["user"]["email"] == unique_email
    temp_password = body["temporary_password"]
    assert temp_password

    # The generated temp password actually works to log in.
    r = client.post("/api/v1/auth/login", json={"email": unique_email, "password": temp_password})
    assert r.status_code == 200, r.text


def test_create_employee_requires_admin_or_hr_manager(client, new_user, unique_email):
    plain = new_user("Plain Employee", role="employee")
    role_id = _role_id(client, plain["headers"], "employee")

    r = client.post(f"{BASE}/employees", headers=plain["headers"], json={
        "full_name": "New Hire",
        "email": unique_email,
        "role_id": role_id,
        "job_title": "Software Engineer",
        "hire_date": "2026-01-15",
    })
    assert r.status_code == 403


def test_my_record_404_then_200_after_onboarding(client, new_user, unique_email):
    admin = new_user("Admin User")
    hire = new_user("Not Onboarded Yet")  # has a login, but no employee record
    assert client.get(f"{BASE}/me", headers=hire["headers"]).status_code == 404

    role_id = _role_id(client, admin["headers"], "employee")
    r = client.post(f"{BASE}/employees", headers=admin["headers"], json={
        "full_name": "Soon Onboarded",
        "email": unique_email,
        "role_id": role_id,
        "job_title": "Designer",
        "hire_date": "2026-02-01",
    })
    assert r.status_code == 201, r.text
    temp_password = r.json()["temporary_password"]

    login = client.post("/api/v1/auth/login", json={"email": unique_email, "password": temp_password})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    me = client.get(f"{BASE}/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["job_title"] == "Designer"


def test_department_create_assign_and_update(client, new_user, unique_email):
    admin = new_user("Admin User")
    role_id = _role_id(client, admin["headers"], "employee")

    dept_name = f"Engineering {unique_email}"
    r = client.post(f"{BASE}/departments", headers=admin["headers"], json={"name": dept_name})
    assert r.status_code == 201, r.text
    dept_id = r.json()["id"]

    r = client.post(f"{BASE}/employees", headers=admin["headers"], json={
        "full_name": "Dept Member",
        "email": unique_email,
        "role_id": role_id,
        "job_title": "Engineer",
        "department_id": dept_id,
        "hire_date": "2026-03-01",
    })
    assert r.status_code == 201, r.text
    employee_id = r.json()["employee"]["id"]
    assert r.json()["employee"]["department"]["name"] == dept_name

    r = client.patch(f"{BASE}/employees/{employee_id}", headers=admin["headers"], json={
        "job_title": "Senior Engineer",
    })
    assert r.status_code == 200, r.text
    assert r.json()["job_title"] == "Senior Engineer"

    r = client.post(f"{BASE}/employees/{employee_id}/terminate", headers=admin["headers"])
    assert r.status_code == 200
    assert r.json()["status"] == "terminated"

    # Terminated employees still show up in the directory (compliance/history).
    listing = client.get(f"{BASE}/employees", headers=admin["headers"])
    assert any(e["id"] == employee_id for e in listing.json())
