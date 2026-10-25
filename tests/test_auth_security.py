from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.auth import Role, authenticate, issue_token, list_users
from app.core.config import settings
from app.db.database import get_connection
from app.main import app
from app.redistribution.workflow import create_batch, record_verification


client = TestClient(app)


def login(username: str, password: str) -> str:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def headers(username: str, password: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {login(username, password)}"}


def user_id(username: str) -> str:
    return next(user["id"] for user in list_users() if user["username"] == username)


def test_authentication_rejects_missing_invalid_and_expired_tokens():
    assert client.get("/api/auth/me").status_code == 401
    assert client.get(
        "/api/auth/me", headers={"Authorization": "Bearer malformed"}
    ).status_code == 401

    expired = jwt.encode(
        {
            "sub": user_id("operator@example.com"),
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "jti": "expired-test-token",
        },
        settings.auth_secret_key,
        algorithm="HS256",
    )
    response = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {expired}"}
    )
    assert response.status_code == 401
    tampered = login("operator@example.com", "OperatorPassword!123") + "tampered"
    assert client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {tampered}"}
    ).status_code == 401

    wrong_key = jwt.encode(
        {
            "sub": user_id("operator@example.com"),
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            "jti": "wrong-key-test-token",
        },
        "wrong-signing-key-that-is-not-configured",
        algorithm="HS256",
    )
    assert client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {wrong_key}"}
    ).status_code == 401


def test_login_rejects_wrong_password_and_disabled_account():
    wrong = client.post(
        "/api/auth/login",
        json={"username": "operator@example.com", "password": "WrongPassword!123"},
    )
    assert wrong.status_code == 401

    with get_connection() as connection:
        connection.execute(
            "UPDATE users SET active = 0 WHERE username = ?",
            ("operator@example.com",),
        )
    assert authenticate("operator@example.com", "OperatorPassword!123") is None
    assert client.post(
        "/api/auth/login",
        json={"username": "operator@example.com", "password": "OperatorPassword!123"},
    ).status_code == 401


def test_user_responses_never_include_password_hash():
    response = client.get("/api/auth/users", headers=headers("admin@example.com", "AdminPassword!123"))
    assert response.status_code == 200
    assert all("password_hash" not in user for user in response.json())


def test_admin_can_create_user_and_change_role_but_operator_cannot():
    created = client.post(
        "/api/auth/users",
        headers=headers("admin@example.com", "AdminPassword!123"),
        json={
            "username": "newuser@example.com",
            "password": "NewUserPassword!123",
            "role": "AUDITOR",
        },
    )
    assert created.status_code == 201
    target_id = created.json()["id"]
    changed = client.patch(
        f"/api/auth/users/{target_id}/role",
        headers=headers("admin@example.com", "AdminPassword!123"),
        json={"role": "KITCHEN_OPERATOR"},
    )
    assert changed.status_code == 200
    denied = client.post(
        "/api/auth/users",
        headers=headers("operator@example.com", "OperatorPassword!123"),
        json={
            "username": "forbidden@example.com",
            "password": "ForbiddenPassword!123",
            "role": "ADMIN",
        },
    )
    assert denied.status_code == 403


def test_role_permissions_reject_verifier_and_auditor_writes():
    payload = {
        "source_name": "Test Kitchen",
        "meal_name": "Rice",
        "prepared_at": "2026-10-14T12:00:00Z",
        "quantity_available": 10,
        "unit": "portions",
    }
    verifier = client.post(
        "/api/redistribution/batches",
        headers=headers("verifier@example.com", "VerifierPassword!123"),
        json=payload,
    )
    assert verifier.status_code == 403

    auditor = client.post(
        "/api/surplus",
        headers=headers("auditor@example.com", "AuditorPassword!123"),
        json={
            "event_date": "2026-10-14",
            "meal_name": "Rice",
            "quantity": 1,
            "status": "identified",
        },
    )
    assert auditor.status_code == 403


def test_service_boundary_rejects_missing_or_wrong_actor():
    batch = create_batch(
        "Kitchen",
        "Rice",
        "2026-10-14T12:00:00Z",
        10,
        "portions",
        actor_id=user_id("operator@example.com"),
    )
    with pytest.raises(ValueError, match="permission"):
        record_verification(
            batch["id"],
            "forged-verifier",
            "approved",
            actor_id=user_id("operator@example.com"),
        )
    with pytest.raises(ValueError, match="actor"):
        record_verification(batch["id"], "forged-verifier", "approved")


def test_audit_records_authenticated_actor_id_not_client_reference():
    operator_id = user_id("operator@example.com")
    batch = create_batch(
        "Kitchen",
        "Rice",
        "2026-10-14T12:00:00Z",
        10,
        "portions",
        actor_id=operator_id,
    )
    with get_connection() as connection:
        event = connection.execute(
            "SELECT actor_id, operator_reference FROM audit_events WHERE batch_id = ?",
            (batch["id"],),
        ).fetchone()
    assert event["actor_id"] == operator_id
    assert event["operator_reference"] == "operator@example.com"


def test_login_rate_limit_bounds_repeated_failures_without_blocking_other_users():
    username = "rate-limit-target@example.com"
    for _ in range(5):
        response = client.post(
            "/api/auth/login",
            json={"username": username, "password": "WrongPassword!123"},
        )
        assert response.status_code == 401
    blocked = client.post(
        "/api/auth/login",
        json={"username": username, "password": "WrongPassword!123"},
    )
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    assert client.post(
        "/api/auth/login",
        json={"username": "admin@example.com", "password": "AdminPassword!123"},
    ).status_code == 200


def test_token_uses_current_database_role_and_requires_subject():
    operator = authenticate("operator@example.com", "OperatorPassword!123")
    assert operator is not None
    token = issue_token(operator)
    with get_connection() as connection:
        connection.execute(
            "UPDATE users SET role = ? WHERE id = ?",
            (Role.AUDITOR.value, operator.id),
        )
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["role"] == Role.AUDITOR.value

    missing_subject = jwt.encode(
        {
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            "jti": "missing-subject",
        },
        settings.auth_secret_key,
        algorithm="HS256",
    )
    assert client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {missing_subject}"}
    ).status_code == 401


def test_direct_user_creation_requires_authenticated_admin_after_bootstrap():
    with pytest.raises(ValueError, match="authenticated actor"):
        from app.core.auth import create_user

        create_user("direct@example.com", "DirectPassword!123", Role.ADMIN)
