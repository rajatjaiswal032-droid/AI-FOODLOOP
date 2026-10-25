from datetime import date, datetime, timezone
from math import isfinite
from uuid import uuid4

from app.core.auth import authorize_actor
from app.db.database import get_connection

MAX_PAGE_SIZE = 100


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _observation_date(value: date | str) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        raise ValueError("observation_date must be a valid date.")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError("observation_date must be a valid ISO date.") from error


def _meal_name(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("meal_name is required.")
    return value.strip()


def _quantity(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative finite number.")
    try:
        quantity = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a non-negative finite number.") from error
    if not isfinite(quantity) or quantity < 0:
        raise ValueError(f"{field_name} must be a non-negative finite number.")
    return quantity


def _notes(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("notes must be text.")
    cleaned = value.strip()
    return cleaned or None


def create_observation(
    observation_date: date | str,
    meal_name: str,
    quantity_prepared: object,
    quantity_consumed: object,
    notes: str | None = None,
    actor_id: str | None = None,
) -> dict:
    actor = authorize_actor(actor_id, "observation_write")
    normalized_date = _observation_date(observation_date)
    normalized_meal = _meal_name(meal_name)
    prepared = _quantity(quantity_prepared, "quantity_prepared")
    consumed = _quantity(quantity_consumed, "quantity_consumed")
    normalized_notes = _notes(notes)
    observation_id = str(uuid4())
    timestamp = _now()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO production_observations
            (id, observation_date, meal_name, quantity_prepared,
             quantity_consumed, notes, created_by, created_at, updated_at,
             supersedes_id, correction_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
            """,
            (
                observation_id,
                normalized_date,
                normalized_meal,
                prepared,
                consumed,
                normalized_notes,
                actor.id,
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            """
            INSERT INTO observation_audit_events
            (id, observation_id, actor_id, event_type, event_at, details)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                observation_id,
                actor.id,
                "observation_created",
                timestamp,
                f"meal_name={normalized_meal};observation_date={normalized_date}",
            ),
        )
        return _get_observation(connection, observation_id)


def correct_observation(
    observation_id: str,
    observation_date: date | str,
    meal_name: str,
    quantity_prepared: object,
    quantity_consumed: object,
    correction_reason: str,
    notes: str | None = None,
    actor_id: str | None = None,
) -> dict:
    actor = authorize_actor(actor_id, "observation_write")
    if not isinstance(observation_id, str) or not observation_id.strip():
        raise ValueError("observation_id is required.")
    if not isinstance(correction_reason, str) or not correction_reason.strip():
        raise ValueError("correction_reason is required.")
    normalized_date = _observation_date(observation_date)
    normalized_meal = _meal_name(meal_name)
    prepared = _quantity(quantity_prepared, "quantity_prepared")
    consumed = _quantity(quantity_consumed, "quantity_consumed")
    normalized_notes = _notes(notes)
    target_id = observation_id.strip()
    corrected_id = str(uuid4())
    timestamp = _now()
    with get_connection() as connection:
        target = connection.execute(
            """
            SELECT id
            FROM production_observations AS original
            WHERE original.id = ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM production_observations AS newer
                  WHERE newer.supersedes_id = original.id
              )
            """,
            (target_id,),
        ).fetchone()
        if target is None:
            exists = connection.execute(
                "SELECT 1 FROM production_observations WHERE id = ?",
                (target_id,),
            ).fetchone()
            if exists is None:
                raise ValueError("Observation was not found.")
            raise ValueError("Observation has already been superseded.")
        connection.execute(
            """
            INSERT INTO production_observations
            (id, observation_date, meal_name, quantity_prepared,
             quantity_consumed, notes, created_by, created_at, updated_at,
             supersedes_id, correction_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                corrected_id,
                normalized_date,
                normalized_meal,
                prepared,
                consumed,
                normalized_notes,
                actor.id,
                timestamp,
                timestamp,
                target_id,
                correction_reason.strip(),
            ),
        )
        connection.execute(
            """
            INSERT INTO observation_audit_events
            (id, observation_id, actor_id, event_type, event_at, details)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                corrected_id,
                actor.id,
                "observation_corrected",
                timestamp,
                f"supersedes_id={target_id};reason={correction_reason.strip()}",
            ),
        )
        return _get_observation(connection, corrected_id)


def get_observation(observation_id: str, actor_id: str | None = None) -> dict:
    authorize_actor(actor_id, "observation_read")
    if not isinstance(observation_id, str) or not observation_id.strip():
        raise ValueError("observation_id is required.")
    with get_connection() as connection:
        return _get_observation(connection, observation_id.strip())


def list_observations(
    actor_id: str | None = None,
    observation_date: date | str | None = None,
    meal_name: str | None = None,
    include_superseded: bool = False,
    limit: int = MAX_PAGE_SIZE,
    offset: int = 0,
) -> list[dict]:
    authorize_actor(actor_id, "observation_read")
    _validate_pagination(limit, offset)
    filters: list[str] = []
    parameters: list[str] = []
    if observation_date is not None:
        filters.append("observation_date = ?")
        parameters.append(_observation_date(observation_date))
    if meal_name is not None:
        filters.append("meal_name = ?")
        parameters.append(_meal_name(meal_name))
    if not include_superseded:
        filters.append(
            """
            NOT EXISTS (
                SELECT 1
                FROM production_observations AS newer
                WHERE newer.supersedes_id = o.id
            )
            """
        )
    query = """
        SELECT o.*, u.username AS created_by_username,
               NOT EXISTS (
                   SELECT 1
                   FROM production_observations AS newer
                   WHERE newer.supersedes_id = o.id
               ) AS is_current
        FROM production_observations o
        JOIN users u ON u.id = o.created_by
    """
    if filters:
        query += " WHERE " + " AND ".join(filters)
    query += " ORDER BY observation_date DESC, created_at DESC, id DESC LIMIT ? OFFSET ?"
    parameters.extend((limit, offset))
    with get_connection() as connection:
        rows = connection.execute(query, parameters).fetchall()
    results = []
    for row in rows:
        observation = dict(row)
        difference = observation["quantity_prepared"] - observation["quantity_consumed"]
        observation["observed_surplus"] = round(max(difference, 0), 2)
        observation["unmet_demand_indicator"] = round(max(-difference, 0), 2)
        results.append(observation)
    return results


def _validate_pagination(limit: int, offset: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError(f"limit must be an integer between 1 and {MAX_PAGE_SIZE}.")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a non-negative integer.")


def _get_observation(connection, observation_id: str) -> dict:
    row = connection.execute(
        """
        SELECT o.*, u.username AS created_by_username,
               NOT EXISTS (
                   SELECT 1
                   FROM production_observations AS newer
                   WHERE newer.supersedes_id = o.id
               ) AS is_current
        FROM production_observations o
        JOIN users u ON u.id = o.created_by
        WHERE o.id = ?
        """,
        (observation_id,),
    ).fetchone()
    if row is None:
        raise ValueError("Observation was not found.")
    result = dict(row)
    result["is_current"] = bool(result["is_current"])
    result["observed_surplus"] = round(
        max(result["quantity_prepared"] - result["quantity_consumed"], 0), 2
    )
    result["unmet_demand_indicator"] = round(
        max(result["quantity_consumed"] - result["quantity_prepared"], 0), 2
    )
    return result
