from datetime import datetime, timezone
from math import isfinite
from uuid import uuid4

from app.db.database import get_connection
from app.core.auth import authorize_actor


DECISIONS = {"pending", "approved", "rejected", "requires_review"}
ASSIGNMENT_STATUSES = {"assigned", "cancelled"}
DELIVERY_STATUSES = {"recorded", "cancelled"}
TERMINAL_BATCH_STATUSES = {"delivered", "disposal_recorded", "cancelled"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a valid ISO-8601 datetime.") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _required_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required.")
    return value.strip()


def _positive_quantity(value: float, field_name: str) -> float:
    try:
        quantity = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a number.") from error
    if not isfinite(quantity) or quantity <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")
    return quantity


def _batch_status(connection, batch_id: str) -> str:
    row = connection.execute(
        """
        SELECT b.quantity_available,
               COALESCE((SELECT SUM(quantity_assigned) FROM assignments
                         WHERE batch_id = ? AND status = 'assigned'), 0) AS assigned,
               COALESCE((SELECT SUM(quantity_delivered) FROM deliveries d
                         JOIN assignments a ON a.id = d.assignment_id
                         WHERE a.batch_id = ? AND d.status = 'recorded'), 0) AS delivered,
               COALESCE((SELECT SUM(quantity_disposed) FROM disposals
                         WHERE batch_id = ?), 0) AS disposed
        FROM surplus_batches b WHERE b.id = ?
        """,
        (batch_id, batch_id, batch_id, batch_id),
    ).fetchone()
    if row is None:
        raise ValueError("Surplus batch was not found.")
    if row["disposed"] >= row["quantity_available"]:
        return "disposal_recorded"
    if row["delivered"] >= row["quantity_available"]:
        return "delivered"
    if row["assigned"] > 0 and row["delivered"] > 0:
        return "partially_delivered"
    if row["assigned"] >= row["quantity_available"]:
        return "assigned"
    if row["assigned"] > 0:
        return "partially_assigned"
    return "eligible"


def _record_status(connection, batch_id: str, new_status: str, operator: str | None, reason: str | None,
                   assignment_id: str | None = None, actor_id: str | None = None) -> None:
    current = connection.execute(
        "SELECT status FROM surplus_batches WHERE id = ?", (batch_id,)
    ).fetchone()
    if current is None:
        raise ValueError("Surplus batch was not found.")
    if current["status"] == new_status:
        return
    connection.execute(
        "UPDATE surplus_batches SET status = ?, updated_at = ? WHERE id = ?",
        (new_status, _now(), batch_id),
    )
    connection.execute(
        """
        INSERT INTO audit_events
        (id, batch_id, assignment_id, previous_status, new_status, event_at,
         actor_id, operator_reference, reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (str(uuid4()), batch_id, assignment_id, current["status"], new_status,
         _now(), actor_id, operator, reason),
    )


def create_batch(
    source_name: str,
    meal_name: str,
    prepared_at: str,
    quantity_available: float,
    unit: str,
    notes: str | None = None,
    actor_id: str | None = None,
) -> dict:
    actor = authorize_actor(actor_id, "batch_create")
    source_name = _required_text(source_name, "source_name")
    meal_name = _required_text(meal_name, "meal_name")
    unit = _required_text(unit, "unit")
    _parse_datetime(prepared_at, "prepared_at")
    quantity_available = _positive_quantity(quantity_available, "quantity_available")
    batch_id = str(uuid4())
    timestamp = _now()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO surplus_batches
            (id, source_name, meal_name, prepared_at, quantity_available, unit,
             status, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending_verification', ?, ?, ?)
            """,
            (batch_id, source_name, meal_name, prepared_at, quantity_available,
             unit, notes, timestamp, timestamp),
        )
        connection.execute(
            """
            INSERT INTO audit_events
            (id, batch_id, previous_status, new_status, event_at,
             actor_id, operator_reference, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (str(uuid4()), batch_id, None, "pending_verification", timestamp,
             actor.id, actor.username, "Batch recorded; human safety verification required."),
        )
        return _get_batch(connection, batch_id)


def _get_batch(connection, batch_id: str) -> dict:
    row = connection.execute(
        "SELECT * FROM surplus_batches WHERE id = ?", (batch_id,)
    ).fetchone()
    if row is None:
        raise ValueError("Surplus batch was not found.")
    batch = dict(row)
    batch.update(_quantities(connection, batch_id))
    return batch


def _quantities(connection, batch_id: str) -> dict[str, float]:
    assigned = connection.execute(
        "SELECT COALESCE(SUM(quantity_assigned), 0) AS value FROM assignments "
        "WHERE batch_id = ? AND status = 'assigned'", (batch_id,)
    ).fetchone()["value"]
    delivered = connection.execute(
        """
        SELECT COALESCE(SUM(d.quantity_delivered), 0) AS value
        FROM deliveries d JOIN assignments a ON a.id = d.assignment_id
        WHERE a.batch_id = ? AND d.status = 'recorded'
        """, (batch_id,)
    ).fetchone()["value"]
    disposed = connection.execute(
        "SELECT COALESCE(SUM(quantity_disposed), 0) AS value FROM disposals "
        "WHERE batch_id = ?", (batch_id,)
    ).fetchone()["value"]
    available = connection.execute(
        "SELECT quantity_available FROM surplus_batches WHERE id = ?",
        (batch_id,),
    ).fetchone()["quantity_available"]
    return {
        "quantity_assigned": assigned,
        "quantity_delivered": delivered,
        "quantity_disposed": disposed,
        "quantity_remaining": max(0, available - assigned - disposed),
    }


def get_batch(batch_id: str) -> dict:
    _required_text(batch_id, "batch_id")
    with get_connection() as connection:
        batch = _get_batch(connection, batch_id)
        batch["quantity_remaining"] = max(
            0,
            batch["quantity_available"] - batch["quantity_assigned"] - batch["quantity_disposed"],
        )
        batch["quantity_undelivered"] = max(
            0, batch["quantity_assigned"] - batch["quantity_delivered"]
        )
        return batch


def list_batches() -> list[dict]:
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id FROM surplus_batches ORDER BY created_at DESC"
        ).fetchall()
    return [get_batch(row["id"]) for row in rows]


def record_verification(
    batch_id: str,
    verifier_reference: str,
    decision: str,
    condition_assessment: str | None = None,
    storage_information: str | None = None,
    expiry_at: str | None = None,
    packaging_observations: str | None = None,
    reason: str | None = None,
    verified_at: str | None = None,
    actor_id: str | None = None,
) -> dict:
    actor = authorize_actor(actor_id, "verification")
    verifier_reference = actor.username
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of: {', '.join(sorted(DECISIONS))}.")
    timestamp = verified_at or _now()
    _parse_datetime(timestamp, "verified_at")
    if expiry_at is not None:
        _parse_datetime(expiry_at, "expiry_at")
    with get_connection() as connection:
        if connection.execute(
            "SELECT 1 FROM surplus_batches WHERE id = ?", (batch_id,)
        ).fetchone() is None:
            raise ValueError("Surplus batch was not found.")
        verification_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO safety_verifications
            (id, batch_id, verifier_reference, verified_at, decision,
             condition_assessment, storage_information, expiry_at,
             packaging_observations, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (verification_id, batch_id, verifier_reference, timestamp, decision,
             condition_assessment, storage_information, expiry_at,
             packaging_observations, reason, _now()),
        )
        approved_evidence = (
            decision == "approved"
            and bool(condition_assessment and condition_assessment.strip())
            and bool(storage_information and storage_information.strip())
            and bool(expiry_at)
            and _parse_datetime(expiry_at, "expiry_at") > datetime.now(timezone.utc)
        )
        new_status = {
            "approved": "eligible" if approved_evidence else "requires_review",
            "rejected": "rejected",
            "requires_review": "requires_review",
            "pending": "pending_verification",
        }[decision]
        _record_status(connection, batch_id, new_status, verifier_reference, reason, actor_id=actor_id)
        row = connection.execute(
            "SELECT * FROM safety_verifications WHERE id = ?", (verification_id,)
        ).fetchone()
        return dict(row)


def _check_eligibility(connection, batch_id: str) -> dict:
    checked_at = _now()
    batch = connection.execute(
            "SELECT * FROM surplus_batches WHERE id = ?", (batch_id,)
        ).fetchone()
    if batch is None:
        return {
            "eligible": False, "status": "not_found",
            "reasons": ["Surplus batch was not found."], "checked_at": checked_at,
        }
    reasons: list[str] = []
    quantities = _quantities(connection, batch_id)
    remaining = batch["quantity_available"] - quantities["quantity_assigned"] - quantities["quantity_disposed"]
    verification = connection.execute(
            "SELECT * FROM safety_verifications WHERE batch_id = ? "
            "ORDER BY verified_at DESC LIMIT 1", (batch_id,)
        ).fetchone()
    if remaining <= 0:
        reasons.append("No quantity remains available for redistribution.")
    if verification is None:
        reasons.append("Human food-safety verification is required.")
    else:
        if verification["decision"] != "approved":
            reasons.append(f"Latest safety decision is '{verification['decision']}'.")
        for field, label in (
            ("condition_assessment", "condition assessment"),
            ("storage_information", "storage information"),
            ("expiry_at", "validated expiry information"),
        ):
            if not verification[field]:
                reasons.append(f"Missing required safety evidence: {label}.")
        if verification["expiry_at"] and _parse_datetime(
                verification["expiry_at"], "expiry_at"
        ) <= datetime.now(timezone.utc):
            reasons.append("The recorded expiry/time limit has passed.")
    status = "eligible" if not reasons else "blocked"
    return {
        "eligible": not reasons, "status": status, "reasons": reasons,
        "checked_at": checked_at,
    }


def check_eligibility(batch_id: str) -> dict:
    with get_connection() as connection:
        return _check_eligibility(connection, batch_id)


def create_recipient(
    name: str,
    contact_reference: str | None = None,
    service_area: str | None = None,
    active: bool = True,
    notes: str | None = None,
    actor_id: str | None = None,
) -> dict:
    authorize_actor(actor_id, "recipient_write")
    name = _required_text(name, "name")
    recipient_id = str(uuid4())
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO recipients
            (id, name, contact_reference, service_area, active, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (recipient_id, name, contact_reference, service_area, int(active), notes, _now()),
        )
        return dict(connection.execute(
            "SELECT * FROM recipients WHERE id = ?", (recipient_id,)
        ).fetchone())


def list_recipients() -> list[dict]:
    with get_connection() as connection:
        return [dict(row) for row in connection.execute(
            "SELECT * FROM recipients ORDER BY name"
        ).fetchall()]


def list_assignments(batch_id: str | None = None) -> list[dict]:
    with get_connection() as connection:
        if batch_id is None:
            rows = connection.execute(
                "SELECT * FROM assignments ORDER BY assigned_at DESC"
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM assignments WHERE batch_id = ? ORDER BY assigned_at DESC",
                (batch_id,),
            ).fetchall()
        return [dict(row) for row in rows]


def create_assignment(
    batch_id: str,
    recipient_id: str,
    quantity_assigned: float,
    operator_reference: str,
    notes: str | None = None,
    actor_id: str | None = None,
) -> dict:
    actor = authorize_actor(actor_id, "assignment")
    quantity_assigned = _positive_quantity(quantity_assigned, "quantity_assigned")
    operator_reference = actor.username
    with get_connection() as connection:
        eligibility = _check_eligibility(connection, batch_id)
        if not eligibility["eligible"]:
            raise ValueError("Batch is not eligible: " + " ".join(eligibility["reasons"]))
        recipient = connection.execute(
            "SELECT * FROM recipients WHERE id = ?", (recipient_id,)
        ).fetchone()
        if recipient is None:
            raise ValueError("Recipient was not found.")
        if not recipient["active"]:
            raise ValueError("Recipient is inactive.")
        batch = connection.execute(
            "SELECT quantity_available FROM surplus_batches WHERE id = ?", (batch_id,)
        ).fetchone()
        quantities = _quantities(connection, batch_id)
        remaining = batch["quantity_available"] - quantities["quantity_assigned"] - quantities["quantity_disposed"]
        if quantity_assigned > remaining:
            raise ValueError("Assignment quantity exceeds the remaining available quantity.")
        assignment_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO assignments
            (id, batch_id, recipient_id, quantity_assigned, assigned_at, status,
             operator_reference, notes)
            VALUES (?, ?, ?, ?, ?, 'assigned', ?, ?)
            """,
            (assignment_id, batch_id, recipient_id, quantity_assigned, _now(),
             operator_reference, notes),
        )
        _record_status(connection, batch_id, _batch_status(connection, batch_id),
                       operator_reference, "Assignment created.", assignment_id, actor_id)
        return dict(connection.execute(
            "SELECT * FROM assignments WHERE id = ?", (assignment_id,)
        ).fetchone())


def record_delivery(
    assignment_id: str,
    quantity_delivered: float,
    operator_reference: str,
    recipient_confirmation: str | None = None,
    notes: str | None = None,
    actor_id: str | None = None,
) -> dict:
    actor = authorize_actor(actor_id, "delivery_disposal")
    quantity_delivered = _positive_quantity(quantity_delivered, "quantity_delivered")
    operator_reference = actor.username
    with get_connection() as connection:
        assignment = connection.execute(
            "SELECT * FROM assignments WHERE id = ?", (assignment_id,)
        ).fetchone()
        if assignment is None:
            raise ValueError("Assignment was not found.")
        delivered = connection.execute(
            "SELECT COALESCE(SUM(quantity_delivered), 0) AS value FROM deliveries "
            "WHERE assignment_id = ? AND status = 'recorded'", (assignment_id,)
        ).fetchone()["value"]
        if quantity_delivered > assignment["quantity_assigned"] - delivered:
            raise ValueError("Delivery quantity exceeds the undelivered assignment quantity.")
        delivery_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO deliveries
            (id, assignment_id, quantity_delivered, delivered_at, status,
             recipient_confirmation, notes)
            VALUES (?, ?, ?, ?, 'recorded', ?, ?)
            """,
            (delivery_id, assignment_id, quantity_delivered, _now(),
             recipient_confirmation, notes),
        )
        _record_status(connection, assignment["batch_id"],
                       _batch_status(connection, assignment["batch_id"]),
                       operator_reference, "Delivery recorded.", assignment_id, actor_id)
        return dict(connection.execute(
            "SELECT * FROM deliveries WHERE id = ?", (delivery_id,)
        ).fetchone())


def record_disposal(
    batch_id: str,
    quantity_disposed: float,
    reason: str,
    operator_reference: str,
    notes: str | None = None,
    actor_id: str | None = None,
) -> dict:
    actor = authorize_actor(actor_id, "delivery_disposal")
    quantity_disposed = _positive_quantity(quantity_disposed, "quantity_disposed")
    reason = _required_text(reason, "reason")
    operator_reference = actor.username
    with get_connection() as connection:
        batch = connection.execute(
            "SELECT quantity_available FROM surplus_batches WHERE id = ?", (batch_id,)
        ).fetchone()
        if batch is None:
            raise ValueError("Surplus batch was not found.")
        quantities = _quantities(connection, batch_id)
        remaining = batch["quantity_available"] - quantities["quantity_assigned"] - quantities["quantity_disposed"]
        if quantity_disposed > remaining:
            raise ValueError(
                "Disposal quantity exceeds the unassigned remaining quantity; "
                "delivered or assigned quantity cannot be disposed."
            )
        disposal_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO disposals
            (id, batch_id, quantity_disposed, disposed_at, reason,
             operator_reference, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (disposal_id, batch_id, quantity_disposed, _now(), reason,
             operator_reference, notes),
        )
        _record_status(connection, batch_id, _batch_status(connection, batch_id),
                       operator_reference, "Disposal recorded.", actor_id=actor_id)
        return dict(connection.execute(
            "SELECT * FROM disposals WHERE id = ?", (disposal_id,)
        ).fetchone())


def get_audit_history(batch_id: str) -> list[dict]:
    with get_connection() as connection:
        if connection.execute(
            "SELECT 1 FROM surplus_batches WHERE id = ?", (batch_id,)
        ).fetchone() is None:
            raise ValueError("Surplus batch was not found.")
        return [dict(row) for row in connection.execute(
            "SELECT * FROM audit_events WHERE batch_id = ? ORDER BY event_at, id",
            (batch_id,),
        ).fetchall()]
