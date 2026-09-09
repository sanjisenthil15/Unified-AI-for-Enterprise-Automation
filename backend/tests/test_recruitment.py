"""Recruitment module regression tests (run against PostgreSQL).

Covers job CRUD, native-enum round-trip, resume upload + local file storage,
and the stats aggregate — the paths most likely to break on a DB migration.
"""

import io

import pytest


@pytest.fixture
def job_id(client, admin_headers) -> int:
    r = client.post("/api/v1/recruitment/jobs", headers=admin_headers, json={
        "title": "Pytest Backend Engineer",
        "description": "Created by the recruitment test suite.",
        "required_skills": "Python, FastAPI, PostgreSQL",
        "min_education": "Bachelor's Degree",
        "experience_level": "mid",
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_create_and_get_job(client, admin_headers, job_id):
    r = client.get(f"/api/v1/recruitment/jobs/{job_id}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["title"] == "Pytest Backend Engineer"


def test_list_jobs_contains_new_job(client, admin_headers, job_id):
    r = client.get("/api/v1/recruitment/jobs", headers=admin_headers)
    assert r.status_code == 200
    assert any(j["id"] == job_id for j in r.json())


def test_update_job_enum_roundtrip(client, admin_headers, job_id):
    r = client.put(f"/api/v1/recruitment/jobs/{job_id}", headers=admin_headers,
                   json={"experience_level": "senior"})
    assert r.status_code == 200
    assert r.json()["experience_level"] == "senior"


def test_resume_upload_and_list(client, admin_headers, job_id):
    pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
    r = client.post(
        f"/api/v1/recruitment/jobs/{job_id}/resumes", headers=admin_headers,
        data={"candidate_name": "Pytest Candidate", "candidate_email": "cand@example.com"},
        files={"resume_file": ("cand.pdf", io.BytesIO(pdf), "application/pdf")},
    )
    assert r.status_code == 201, r.text
    resume_id = r.json()["id"]

    r = client.get(f"/api/v1/recruitment/jobs/{job_id}/resumes", headers=admin_headers)
    assert r.status_code == 200
    assert any(x["id"] == resume_id for x in r.json())

    client.delete(f"/api/v1/recruitment/resumes/{resume_id}", headers=admin_headers)


def test_recruitment_requires_auth(client):
    r = client.get("/api/v1/recruitment/jobs")
    assert r.status_code in (401, 403)


def test_stats(client, admin_headers):
    r = client.get("/api/v1/recruitment/stats", headers=admin_headers)
    assert r.status_code == 200
    assert "open_positions" in r.json()
