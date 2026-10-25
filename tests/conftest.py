import pytest

from app.core.auth import Role, bootstrap_admin, create_user, list_users
from app.core.config import settings
from app.db.database import initialize_database


@pytest.fixture(autouse=True)
def isolated_application_database(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "foodloop-test.db"))
    monkeypatch.setattr(
        settings,
        "auth_secret_key",
        "test-only-secret-key-with-at-least-32-characters",
    )
    initialize_database()
    bootstrap_admin("admin@example.com", "AdminPassword!123")
    admin_id = next(user["id"] for user in list_users() if user["username"] == "admin@example.com")
    create_user("operator@example.com", "OperatorPassword!123", Role.KITCHEN_OPERATOR, actor_id=admin_id)
    create_user("verifier@example.com", "VerifierPassword!123", Role.FOOD_SAFETY_VERIFIER, actor_id=admin_id)
    create_user("auditor@example.com", "AuditorPassword!123", Role.AUDITOR, actor_id=admin_id)
