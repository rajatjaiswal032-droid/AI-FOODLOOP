from datetime import datetime, timedelta, timezone

import pytest

from app.core.auth import Role, bootstrap_admin, create_user, list_users
from app.core.config import settings
from app.db.database import initialize_database
from app.redistribution.workflow import (
    check_eligibility,
    create_assignment,
    create_batch,
    create_recipient,
    get_audit_history,
    get_batch,
    record_delivery,
    record_disposal,
    record_verification,
)


@pytest.fixture
def workflow_database(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "workflow.db"))
    initialize_database()
    bootstrap_admin("admin@example.com", "AdminPassword!123")
    admin_id = actor(Role.ADMIN)
    create_user("operator@example.com", "OperatorPassword!123", Role.KITCHEN_OPERATOR, actor_id=admin_id)
    create_user("verifier@example.com", "VerifierPassword!123", Role.FOOD_SAFETY_VERIFIER, actor_id=admin_id)


def actor(role: Role) -> str:
    return next(user["id"] for user in list_users() if user["role"] == role.value)


def future_expiry() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()


def create_test_batch():
    return create_batch(
        "Campus Kitchen",
        "Vegetable Rice",
        "2026-10-14T12:00:00+00:00",
        100,
        "portions",
        actor_id=actor(Role.KITCHEN_OPERATOR),
    )


def approve(batch_id: str):
    return record_verification(
        batch_id,
        "operator-verified",
        "approved",
        condition_assessment="Intact and suitable for review",
        storage_information="Stored according to local procedure",
        expiry_at=future_expiry(),
        reason="Authorized human review completed",
        actor_id=actor(Role.FOOD_SAFETY_VERIFIER),
    )


def test_valid_batch_creation_and_pending_eligibility(workflow_database):
    batch = create_test_batch()
    assert batch["status"] == "pending_verification"
    assert batch["quantity_available"] == 100
    assert batch["quantity_assigned"] == 0
    assert batch["quantity_delivered"] == 0
    assert batch["quantity_disposed"] == 0
    assert batch["quantity_remaining"] == 100
    result = check_eligibility(batch["id"])
    assert result["eligible"] is False
    assert "human food-safety verification" in " ".join(result["reasons"]).lower()


@pytest.mark.parametrize("quantity", [0, -1, float("nan"), float("inf")])
def test_invalid_batch_quantity_rejected(workflow_database, quantity):
    with pytest.raises(ValueError, match="greater than zero"):
        create_batch(
            "Kitchen", "Rice", "2026-10-14T12:00:00Z", quantity, "kg",
            actor_id=actor(Role.KITCHEN_OPERATOR),
        )


def test_missing_batch_fields_rejected(workflow_database):
    with pytest.raises(ValueError, match="source_name"):
        create_batch(
            "", "Rice", "2026-10-14T12:00:00Z", 1, "kg",
            actor_id=actor(Role.KITCHEN_OPERATOR),
        )
    with pytest.raises(ValueError, match="prepared_at"):
        create_batch(
            "Kitchen", "Rice", "bad-date", 1, "kg",
            actor_id=actor(Role.KITCHEN_OPERATOR),
        )


def test_rejected_and_incomplete_verification_block(workflow_database):
    batch = create_test_batch()
    record_verification(
        batch["id"], "operator", "rejected",
        reason="Condition not acceptable", actor_id=actor(Role.FOOD_SAFETY_VERIFIER),
    )
    result = check_eligibility(batch["id"])
    assert result["eligible"] is False
    assert "rejected" in " ".join(result["reasons"])

    batch = create_test_batch()
    record_verification(
        batch["id"], "operator", "approved", actor_id=actor(Role.FOOD_SAFETY_VERIFIER)
    )
    result = check_eligibility(batch["id"])
    assert result["eligible"] is False
    assert "missing required safety evidence" in " ".join(result["reasons"]).lower()


def test_approved_verification_and_expiry_policy(workflow_database):
    batch = create_test_batch()
    approve(batch["id"])
    assert check_eligibility(batch["id"])["eligible"] is True

    expired = create_test_batch()
    record_verification(
        expired["id"],
        "operator-verified",
        "approved",
        condition_assessment="Recorded",
        storage_information="Recorded",
        expiry_at="2020-01-01T00:00:00+00:00",
        reason="Review completed",
        actor_id=actor(Role.FOOD_SAFETY_VERIFIER),
    )
    result = check_eligibility(expired["id"])
    assert result["eligible"] is False
    assert "expiry" in " ".join(result["reasons"]).lower()


def test_assignment_requires_eligibility_and_active_recipient(workflow_database):
    batch = create_test_batch()
    recipient = create_recipient(
        "Community Center", active=False, actor_id=actor(Role.KITCHEN_OPERATOR)
    )
    with pytest.raises(ValueError, match="not eligible"):
        create_assignment(
            batch["id"], recipient["id"], 10, "operator",
            actor_id=actor(Role.KITCHEN_OPERATOR),
        )
    approve(batch["id"])
    with pytest.raises(ValueError, match="inactive"):
        create_assignment(
            batch["id"], recipient["id"], 10, "operator",
            actor_id=actor(Role.KITCHEN_OPERATOR),
        )


def test_assignments_are_bounded_and_delivery_is_partial(workflow_database):
    batch = create_test_batch()
    approve(batch["id"])
    first = create_recipient("Community Center", actor_id=actor(Role.KITCHEN_OPERATOR))
    second = create_recipient("Shelter", actor_id=actor(Role.KITCHEN_OPERATOR))
    assignment = create_assignment(
        batch["id"], first["id"], 60, "operator",
        actor_id=actor(Role.KITCHEN_OPERATOR),
    )
    with pytest.raises(ValueError, match="exceeds"):
        create_assignment(
            batch["id"], second["id"], 41, "operator",
            actor_id=actor(Role.KITCHEN_OPERATOR),
        )
    with pytest.raises(ValueError, match="greater than zero"):
        record_delivery(
            assignment["id"], 0, "operator", actor_id=actor(Role.KITCHEN_OPERATOR)
        )
    record_delivery(
        assignment["id"], 25, "operator", actor_id=actor(Role.KITCHEN_OPERATOR)
    )
    current = get_batch(batch["id"])
    assert current["quantity_delivered"] == 25
    assert current["quantity_undelivered"] == 35
    assert current["quantity_remaining"] == 40
    with pytest.raises(ValueError, match="undelivered"):
        record_delivery(
            assignment["id"], 36, "operator", actor_id=actor(Role.KITCHEN_OPERATOR)
        )


def test_disposal_cannot_double_count_assigned_quantity(workflow_database):
    batch = create_test_batch()
    approve(batch["id"])
    recipient = create_recipient("Community Center", actor_id=actor(Role.KITCHEN_OPERATOR))
    assignment = create_assignment(
        batch["id"], recipient["id"], 60, "operator",
        actor_id=actor(Role.KITCHEN_OPERATOR),
    )
    with pytest.raises(ValueError, match="assigned"):
        record_disposal(
            batch["id"], 41, "No safe recipient", "operator",
            actor_id=actor(Role.KITCHEN_OPERATOR),
        )
    record_delivery(
        assignment["id"], 60, "operator", "Confirmed by recipient",
        actor_id=actor(Role.KITCHEN_OPERATOR),
    )
    record_disposal(
        batch["id"], 40, "No remaining unassigned quantity", "operator",
        actor_id=actor(Role.KITCHEN_OPERATOR),
    )
    final = get_batch(batch["id"])
    assert final["quantity_delivered"] == 60
    assert final["quantity_disposed"] == 40
    assert final["quantity_remaining"] == 0
    assert final["quantity_undelivered"] == 0
    with pytest.raises(ValueError, match="assigned"):
        record_disposal(
            batch["id"], 1, "No remaining unassigned quantity", "operator",
            actor_id=actor(Role.KITCHEN_OPERATOR),
        )


def test_audit_history_preserves_transitions(workflow_database):
    batch = create_test_batch()
    approve(batch["id"])
    recipient = create_recipient("Community Center", actor_id=actor(Role.KITCHEN_OPERATOR))
    assignment = create_assignment(
        batch["id"], recipient["id"], 10, "operator",
        actor_id=actor(Role.KITCHEN_OPERATOR),
    )
    record_delivery(
        assignment["id"], 10, "operator", actor_id=actor(Role.KITCHEN_OPERATOR)
    )
    history = get_audit_history(batch["id"])
    assert history[0]["new_status"] == "pending_verification"
    assert any(event["new_status"] == "eligible" for event in history)
    assert any(event["new_status"] == "partially_assigned" for event in history)
    assert any(event["new_status"] == "partially_delivered" for event in history)
