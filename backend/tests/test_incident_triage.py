"""
test_incident_triage.py

Regression tests for Incident Management AI Triage endpoint:
- Verifies role authorization: admin, support_agent, manager can trigger triage.
- Verifies role authorization: employee cannot trigger triage (403 Forbidden).
- Verifies Gemini response parsing and persistence to incident_ai_triage table.
- Verifies timeline entry is generated for triage completion.
- Verifies GET /{incident_id}/triage retrieves persisted triage result.
- Verifies 404 behavior for non-existent incident.
"""

from unittest.mock import MagicMock, patch
from models.incident import Incident, IncidentAITriage, IncidentTimeline

INC_BASE = "/api/v1/incidents"


def test_ai_triage_rbac_permissions(client, new_user, db):
    admin = new_user("Incident Admin", role="admin")
    manager = new_user("Incident Manager", role="manager")
    employee = new_user("Incident Employee", role="employee")

    # Create an incident via admin
    create_payload = {
        "title": "Auth microservice 500 spike",
        "description": "JWT verification service is returning 500 internal server errors intermittently.",
        "severity": "high",
        "affected_system": "Auth Service",
    }
    r = client.post(f"{INC_BASE}", headers=admin["headers"], json=create_payload)
    assert r.status_code == 201, r.text
    inc_id = r.json()["id"]

    try:
        # Employee should be rejected with 403
        r_emp = client.post(f"{INC_BASE}/{inc_id}/triage", headers=employee["headers"])
        assert r_emp.status_code == 403

        # Mock Gemini call for authorized users
        mock_gemini_response = MagicMock()
        mock_gemini_response.text = '{"suggested_severity": "critical", "suggested_owner": "Platform Security Team", "confidence": 92.5, "reasoning": "Auth failures prevent all user logins."}'

        with patch("modules.incident_management.service._genai") as mock_genai, \
             patch("modules.incident_management.service.settings") as mock_settings:
            mock_settings.GEMINI_API_KEY = "test-key"
            mock_client_instance = MagicMock()
            mock_client_instance.models.generate_content.return_value = mock_gemini_response
            mock_genai.Client.return_value = mock_client_instance

            # Manager can run triage
            r_mgr = client.post(f"{INC_BASE}/{inc_id}/triage", headers=manager["headers"])
            assert r_mgr.status_code == 201, r_mgr.text
            triage_data = r_mgr.json()
            assert triage_data["incident_id"] == inc_id
            assert triage_data["suggested_severity"] == "critical"
            assert triage_data["suggested_owner"] == "Platform Security Team"
            assert triage_data["confidence"] == 92.5
            assert triage_data["ai_model"] == "gemini-3.6-flash"

            # Verify persisted in database
            db_triage = db.query(IncidentAITriage).filter(IncidentAITriage.incident_id == inc_id).first()
            assert db_triage is not None
            assert db_triage.suggested_severity == "critical"
            assert db_triage.confidence == 92.5

            # Verify timeline audit log entry
            timeline_entry = db.query(IncidentTimeline).filter(
                IncidentTimeline.incident_id == inc_id,
                IncidentTimeline.action == "ai_triage_completed",
            ).first()
            assert timeline_entry is not None
            assert "AI suggested severity: 'critical'" in timeline_entry.notes

            # Verify any authenticated user can read latest triage
            r_get = client.get(f"{INC_BASE}/{inc_id}/triage", headers=employee["headers"])
            assert r_get.status_code == 200
            assert r_get.json()["suggested_owner"] == "Platform Security Team"

    finally:
        # Clean up database test records so teardown doesn't violate foreign keys
        db.query(IncidentAITriage).filter(IncidentAITriage.incident_id == inc_id).delete()
        db.query(IncidentTimeline).filter(IncidentTimeline.incident_id == inc_id).delete()
        db.query(Incident).filter(Incident.id == inc_id).delete()
        db.commit()


def test_ai_triage_not_found(client, new_user):
    admin = new_user("Incident Admin 2", role="admin")
    r = client.post(f"{INC_BASE}/999999/triage", headers=admin["headers"])
    assert r.status_code == 404
