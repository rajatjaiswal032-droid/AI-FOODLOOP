import sqlite3
from contextlib import contextmanager
from datetime import date

import pytest

from app.core.auth import list_users
from app.db.database import get_connection, initialize_database
import app.observations.service as observation_service
from app.observations.service import (
    correct_observation,
    create_observation,
    get_observation,
    list_observations,
)


def user_id(username: str) -> str:
    return next(user["id"] for user in list_users() if user["username"] == username)


def test_authorized_operator_can_create_retrieve_and_filter_observation():
    operator_id = user_id("operator@example.com")
    created = create_observation(
        date(2026, 10, 15),
        "Rice",
        100,
        80,
        "Lunch aggregate",
        operator_id,
    )

    assert created["id"]
    assert created["created_by"] == operator_id
    assert created["created_by_username"] == "operator@example.com"
    assert created["observed_surplus"] == 20
    assert created["unmet_demand_indicator"] == 0
    assert get_observation(created["id"], user_id("auditor@example.com"))["id"] == created["id"]
    assert list_observations(user_id("admin@example.com"), "2026-10-15", "Rice")[0]["id"] == created["id"]


def test_zero_quantities_are_preserved():
    created = create_observation(
        "2026-10-15", "Rice", 0, 0, actor_id=user_id("operator@example.com")
    )
    assert created["quantity_prepared"] == 0
    assert created["quantity_consumed"] == 0
    assert created["observed_surplus"] == 0


@pytest.mark.parametrize(
    ("prepared", "consumed"),
    [(-1, 1), (1, -1), (True, 1), (1, False), (float("nan"), 1), (1, float("inf"))],
)
def test_invalid_quantities_are_rejected(prepared, consumed):
    with pytest.raises(ValueError, match="non-negative finite"):
        create_observation(
            "2026-10-15",
            "Rice",
            prepared,
            consumed,
            actor_id=user_id("operator@example.com"),
        )


@pytest.mark.parametrize(
    ("observation_date", "meal_name"),
    [("not-a-date", "Rice"), ("2026-10-15", ""), ("2026-10-15", "   ")],
)
def test_invalid_identity_fields_are_rejected(observation_date, meal_name):
    with pytest.raises(ValueError):
        create_observation(
            observation_date,
            meal_name,
            1,
            1,
            actor_id=user_id("operator@example.com"),
        )


def test_anonymous_and_unauthorized_writes_and_reads_are_rejected():
    with pytest.raises(ValueError, match="actor"):
        create_observation("2026-10-15", "Rice", 1, 1)
    with pytest.raises(ValueError, match="permission"):
        create_observation(
            "2026-10-15",
            "Rice",
            1,
            1,
            actor_id=user_id("verifier@example.com"),
        )
    assert list_observations(user_id("operator@example.com")) == []


def test_multiple_records_are_preserved_and_not_silently_overwritten():
    operator_id = user_id("operator@example.com")
    first = create_observation("2026-10-15", "Rice", 100, 80, actor_id=operator_id)
    second = create_observation("2026-10-15", "Rice", 50, 40, actor_id=operator_id)

    records = list_observations(operator_id, "2026-10-15", "Rice")
    assert {record["id"] for record in records} == {first["id"], second["id"]}


def test_creation_and_audit_are_transactionally_consistent(monkeypatch):
    operator_id = user_id("operator@example.com")
    original_get_connection = observation_service.get_connection

    @contextmanager
    def failing_connection():
        with original_get_connection() as connection:
            class ConnectionProxy:
                def execute(self, query, parameters=()):
                    if "observation_audit_events" in query:
                        raise sqlite3.IntegrityError("simulated audit failure")
                    return connection.execute(query, parameters)

            yield ConnectionProxy()

    monkeypatch.setattr(observation_service, "get_connection", failing_connection)
    with pytest.raises(sqlite3.IntegrityError, match="simulated audit failure"):
        create_observation("2026-10-15", "Rice", 1, 1, actor_id=operator_id)
    monkeypatch.setattr(observation_service, "get_connection", original_get_connection)
    assert list_observations(operator_id, "2026-10-15", "Rice") == []
    with get_connection() as connection:
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM observation_audit_events"
        ).fetchone()["count"] == 0


def test_repeated_initialization_preserves_users_and_observations():
    operator_id = user_id("operator@example.com")
    created = create_observation("2026-10-15", "Rice", 1, 1, actor_id=operator_id)
    initialize_database()
    assert user_id("admin@example.com")
    assert get_observation(created["id"], operator_id)["id"] == created["id"]


def test_observation_audit_records_authenticated_actor():
    operator_id = user_id("operator@example.com")
    created = create_observation("2026-10-15", "Rice", 1, 1, actor_id=operator_id)
    with get_connection() as connection:
        event = connection.execute(
            "SELECT observation_id, actor_id, event_type FROM observation_audit_events"
        ).fetchone()
    assert event["observation_id"] == created["id"]
    assert event["actor_id"] == operator_id
    assert event["event_type"] == "observation_created"


def test_correction_preserves_original_and_marks_latest_record_current():
    operator_id = user_id("operator@example.com")
    original = create_observation(
        "2026-10-15", "Rice", 100, 80, actor_id=operator_id
    )
    corrected = correct_observation(
        original["id"],
        "2026-10-15",
        "Rice",
        90,
        80,
        "Corrected prepared count from kitchen log.",
        actor_id=operator_id,
    )

    assert corrected["supersedes_id"] == original["id"]
    assert corrected["correction_reason"] == "Corrected prepared count from kitchen log."
    assert corrected["is_current"] is True
    assert get_observation(original["id"], operator_id)["quantity_prepared"] == 100
    assert get_observation(original["id"], operator_id)["is_current"] is False
    current = list_observations(operator_id, "2026-10-15", "Rice")
    assert [record["id"] for record in current] == [corrected["id"]]
    history = list_observations(
        operator_id, "2026-10-15", "Rice", include_superseded=True
    )
    assert {record["id"] for record in history} == {original["id"], corrected["id"]}


def test_correction_requires_reason_and_rejects_superseded_targets():
    operator_id = user_id("operator@example.com")
    original = create_observation(
        "2026-10-15", "Rice", 100, 80, actor_id=operator_id
    )
    with pytest.raises(ValueError, match="correction_reason"):
        correct_observation(
            original["id"], "2026-10-15", "Rice", 100, 80, " ",
            actor_id=operator_id,
        )
    correct_observation(
        original["id"], "2026-10-15", "Rice", 90, 80, "Corrected count.",
        actor_id=operator_id,
    )
    with pytest.raises(ValueError, match="already been superseded"):
        correct_observation(
            original["id"], "2026-10-15", "Rice", 80, 70, "Second correction.",
            actor_id=operator_id,
        )


def test_history_pagination_is_bounded_and_deterministic():
    operator_id = user_id("operator@example.com")
    for quantity in (1, 2, 3):
        create_observation(
            "2026-10-15", "Rice", quantity, quantity, actor_id=operator_id
        )
    first_page = list_observations(operator_id, limit=2, offset=0)
    second_page = list_observations(operator_id, limit=2, offset=2)
    assert len(first_page) == 2
    assert len(second_page) == 1
    assert {row["id"] for row in first_page}.isdisjoint(
        row["id"] for row in second_page
    )
    with pytest.raises(ValueError, match="between 1 and"):
        list_observations(operator_id, limit=101)
    with pytest.raises(ValueError, match="non-negative"):
        list_observations(operator_id, offset=-1)
