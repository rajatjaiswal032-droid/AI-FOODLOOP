from datetime import date

from app.db.database import get_connection
from app.core.auth import authorize_actor


ALLOWED_STATUSES = {"identified", "redistributed", "disposed", "unresolved"}


def create_surplus_event(
    event_date: date,
    meal_name: str,
    quantity: float,
    status: str,
    recipient: str | None = None,
    notes: str | None = None,
    actor_id: str | None = None,
) -> dict:
    authorize_actor(actor_id, "surplus_write")
    if quantity < 0:
        raise ValueError("quantity must be non-negative.")
    if status not in ALLOWED_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}.")

    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO surplus_events
            (event_date, meal_name, quantity, status, recipient, notes)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_date.isoformat(), meal_name.strip(), quantity, status, recipient, notes),
        )
        row = connection.execute(
            "SELECT * FROM surplus_events WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(row)


def list_surplus_events(actor_id: str | None = None) -> list[dict]:
    authorize_actor(actor_id, "surplus_read")
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM surplus_events ORDER BY event_date DESC, id DESC"
        ).fetchall()
    return [dict(row) for row in rows]
