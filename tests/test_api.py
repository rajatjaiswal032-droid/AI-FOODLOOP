from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def token(username: str, password: str) -> str:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(username: str, password: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token(username, password)}


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_forecast_api():
    headers = {"Authorization": f"Bearer {token('operator@example.com', 'OperatorPassword!123')}"}
    response = client.post(
        "/api/forecast",
        headers=headers,
        json={
            "records": [
                {
                    "date": "2026-01-01",
                    "meal_name": "Rice",
                    "quantity_prepared": 100,
                    "quantity_consumed": 80,
                },
                {
                    "date": "2026-01-02",
                    "meal_name": "Rice",
                    "quantity_prepared": 100,
                    "quantity_consumed": 90,
                },
            ],
            "meal_name": "Rice",
            "forecast_date": "2026-01-03",
            "safety_buffer": 0.1,
        },
    )
    assert response.status_code == 200
    assert response.json()["recommended_production"] == 93.5


def test_observation_api_enforces_roles_and_persists_audit():
    payload = {
        "observation_date": "2026-10-15",
        "meal_name": "Rice",
        "quantity_prepared": 100,
        "quantity_consumed": 80,
    }
    assert client.post("/api/observations", json=payload).status_code == 401
    verifier = client.post(
        "/api/observations",
        headers=headers("verifier@example.com", "VerifierPassword!123"),
        json=payload,
    )
    assert verifier.status_code == 403

    created = client.post(
        "/api/observations",
        headers=headers("operator@example.com", "OperatorPassword!123"),
        json=payload,
    )
    assert created.status_code == 201
    observation_id = created.json()["id"]
    assert created.json()["created_by_username"] == "operator@example.com"
    fetched = client.get(
        f"/api/observations/{observation_id}",
        headers=headers("auditor@example.com", "AuditorPassword!123"),
    )
    assert fetched.status_code == 200
    history = client.get(
        "/api/observations?observation_date=2026-10-15&meal_name=Rice",
        headers=headers("auditor@example.com", "AuditorPassword!123"),
    )
    assert history.status_code == 200
    assert history.json()[0]["observed_surplus"] == 20


def test_observation_api_rejects_invalid_quantities():
    response = client.post(
        "/api/observations",
        headers=headers("operator@example.com", "OperatorPassword!123"),
        json={
            "observation_date": "2026-10-15",
            "meal_name": "Rice",
            "quantity_prepared": -1,
            "quantity_consumed": 1,
        },
    )
    assert response.status_code == 422


def test_observation_correction_api_preserves_original_record():
    created = client.post(
        "/api/observations",
        headers=headers("operator@example.com", "OperatorPassword!123"),
        json={
            "observation_date": "2026-10-15",
            "meal_name": "Rice",
            "quantity_prepared": 100,
            "quantity_consumed": 80,
        },
    )
    assert created.status_code == 201
    original_id = created.json()["id"]
    corrected = client.post(
        f"/api/observations/{original_id}/correction",
        headers=headers("operator@example.com", "OperatorPassword!123"),
        json={
            "observation_date": "2026-10-15",
            "meal_name": "Rice",
            "quantity_prepared": 90,
            "quantity_consumed": 80,
            "correction_reason": "Updated from the signed kitchen log.",
        },
    )
    assert corrected.status_code == 201
    assert corrected.json()["supersedes_id"] == original_id
    history = client.get(
        "/api/observations?observation_date=2026-10-15&meal_name=Rice",
        headers=headers("auditor@example.com", "AuditorPassword!123"),
    )
    assert history.status_code == 200
    assert [row["id"] for row in history.json()] == [corrected.json()["id"]]


def test_redistribution_api_requires_verification_before_assignment():
    operator_headers = {
        "Authorization": f"Bearer {token('operator@example.com', 'OperatorPassword!123')}"
    }
    verifier_headers = {
        "Authorization": f"Bearer {token('verifier@example.com', 'VerifierPassword!123')}"
    }
    batch_response = client.post(
        "/api/redistribution/batches",
        headers=operator_headers,
        json={
            "source_name": "Test Kitchen",
            "meal_name": "Rice",
            "prepared_at": "2026-10-14T12:00:00Z",
            "quantity_available": 10,
            "unit": "portions",
        },
    )
    assert batch_response.status_code == 201
    batch_id = batch_response.json()["id"]
    blocked = client.get(
        f"/api/redistribution/batches/{batch_id}/eligibility",
        headers=operator_headers,
    )
    assert blocked.status_code == 200
    assert blocked.json()["eligible"] is False

    verification = client.post(
        f"/api/redistribution/batches/{batch_id}/verification",
        headers=verifier_headers,
        json={
            "verifier_reference": "test-operator",
            "decision": "approved",
            "condition_assessment": "Recorded",
            "storage_information": "Recorded",
            "expiry_at": (
                datetime.now(timezone.utc) + timedelta(days=1)
            ).isoformat(),
            "reason": "Test human review",
        },
    )
    assert verification.status_code == 201
    recipient = client.post(
        "/api/redistribution/recipients",
        headers=operator_headers,
        json={"name": "Test Recipient"},
    )
    assert recipient.status_code == 201
    assignment = client.post(
        f"/api/redistribution/batches/{batch_id}/assignments",
        headers=operator_headers,
        json={
            "recipient_id": recipient.json()["id"],
            "quantity_assigned": 4,
            "operator_reference": "test-operator",
        },
    )
    assert assignment.status_code == 201
    delivery = client.post(
        f"/api/redistribution/assignments/{assignment.json()['id']}/deliveries",
        headers=operator_headers,
        json={
            "quantity_delivered": 2,
            "operator_reference": "test-operator",
        },
    )
    assert delivery.status_code == 201
