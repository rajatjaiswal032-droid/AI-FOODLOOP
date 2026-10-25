import sqlite3

from app.core.config import settings
from app.db.database import initialize_database


def test_legacy_audit_schema_migrates_without_losing_history(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy.db"
    monkeypatch.setattr(settings, "database_path", str(database_path))
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE surplus_batches (
                id TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                meal_name TEXT NOT NULL,
                prepared_at TEXT NOT NULL,
                quantity_available REAL NOT NULL,
                unit TEXT NOT NULL,
                status TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE audit_events (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                assignment_id TEXT,
                previous_status TEXT,
                new_status TEXT NOT NULL,
                event_at TEXT NOT NULL,
                operator_reference TEXT,
                reason TEXT
            );
            INSERT INTO surplus_batches VALUES
                ('batch-1', 'Kitchen', 'Rice', '2026-10-14T12:00:00Z',
                 10, 'portions', 'pending_verification', NULL,
                 '2026-10-14T12:00:00Z', '2026-10-14T12:00:00Z');
            INSERT INTO audit_events VALUES
                ('event-1', 'batch-1', NULL, NULL, 'pending_verification',
                 '2026-10-14T12:00:00Z', 'legacy-operator', 'historical record');
            """
        )

    initialize_database()
    initialize_database()

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(audit_events)")
        }
        event = connection.execute(
            "SELECT * FROM audit_events WHERE id = 'event-1'"
        ).fetchone()
    assert "actor_id" in columns
    assert event["operator_reference"] == "legacy-operator"
    assert event["new_status"] == "pending_verification"


def test_observation_tables_are_added_idempotently_to_existing_database(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "existing.db"
    monkeypatch.setattr(settings, "database_path", str(database_path))
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                active INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "user-1",
                "existing@example.com",
                "hash",
                "ADMIN",
                1,
                "2026-10-15T00:00:00+00:00",
                "2026-10-15T00:00:00+00:00",
            ),
        )

    initialize_database()
    initialize_database()

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        user = connection.execute(
            "SELECT username, role FROM users WHERE id = 'user-1'"
        ).fetchone()
    assert "production_observations" in tables
    assert "observation_audit_events" in tables
    assert user == ("existing@example.com", "ADMIN")


def test_existing_observation_rows_receive_correction_columns(tmp_path, monkeypatch):
    database_path = tmp_path / "legacy-observations.db"
    monkeypatch.setattr(settings, "database_path", str(database_path))
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                active INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE production_observations (
                id TEXT PRIMARY KEY,
                observation_date TEXT NOT NULL,
                meal_name TEXT NOT NULL,
                quantity_prepared REAL NOT NULL,
                quantity_consumed REAL NOT NULL,
                notes TEXT,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO users VALUES
                ('user-1', 'operator@example.com', 'hash', 'KITCHEN_OPERATOR',
                 1, '2026-10-15T00:00:00+00:00', '2026-10-15T00:00:00+00:00');
            INSERT INTO production_observations VALUES
                ('observation-1', '2026-10-15', 'Rice', 10, 8, NULL, 'user-1',
                 '2026-10-15T00:00:00+00:00', '2026-10-15T00:00:00+00:00');
            """
        )

    initialize_database()
    initialize_database()

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(production_observations)"
            )
        }
        row = connection.execute(
            "SELECT id, quantity_prepared FROM production_observations"
        ).fetchone()
    assert {"supersedes_id", "correction_reason"} <= columns
    assert row == ("observation-1", 10)
