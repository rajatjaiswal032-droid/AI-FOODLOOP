import sqlite3
from pathlib import Path

from app.core.config import settings


def _open_connection() -> sqlite3.Connection:
    database_path = Path(settings.database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with _open_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS surplus_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                meal_name TEXT NOT NULL,
                quantity REAL NOT NULL CHECK(quantity >= 0),
                status TEXT NOT NULL,
                recipient TEXT,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                active INTEGER NOT NULL CHECK(active IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_events (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                actor_id TEXT,
                event_type TEXT NOT NULL,
                event_at TEXT NOT NULL,
                details TEXT
            );
            CREATE TABLE IF NOT EXISTS surplus_batches (
                id TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                meal_name TEXT NOT NULL,
                prepared_at TEXT NOT NULL,
                quantity_available REAL NOT NULL CHECK(quantity_available > 0),
                unit TEXT NOT NULL,
                status TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS safety_verifications (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL REFERENCES surplus_batches(id),
                verifier_reference TEXT NOT NULL,
                verified_at TEXT NOT NULL,
                decision TEXT NOT NULL,
                condition_assessment TEXT,
                storage_information TEXT,
                expiry_at TEXT,
                packaging_observations TEXT,
                reason TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS recipients (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                contact_reference TEXT,
                service_area TEXT,
                active INTEGER NOT NULL CHECK(active IN (0, 1)),
                notes TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS assignments (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL REFERENCES surplus_batches(id),
                recipient_id TEXT NOT NULL REFERENCES recipients(id),
                quantity_assigned REAL NOT NULL CHECK(quantity_assigned > 0),
                assigned_at TEXT NOT NULL,
                status TEXT NOT NULL,
                operator_reference TEXT NOT NULL,
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                id TEXT PRIMARY KEY,
                assignment_id TEXT NOT NULL REFERENCES assignments(id),
                quantity_delivered REAL NOT NULL CHECK(quantity_delivered > 0),
                delivered_at TEXT NOT NULL,
                status TEXT NOT NULL,
                recipient_confirmation TEXT,
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS disposals (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL REFERENCES surplus_batches(id),
                quantity_disposed REAL NOT NULL CHECK(quantity_disposed > 0),
                disposed_at TEXT NOT NULL,
                reason TEXT NOT NULL,
                operator_reference TEXT NOT NULL,
                notes TEXT
            );
            CREATE TABLE IF NOT EXISTS audit_events (
                id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL REFERENCES surplus_batches(id),
                assignment_id TEXT,
                previous_status TEXT,
                new_status TEXT NOT NULL,
                event_at TEXT NOT NULL,
                actor_id TEXT,
                operator_reference TEXT,
                reason TEXT
            );
            CREATE TABLE IF NOT EXISTS production_observations (
                id TEXT PRIMARY KEY,
                observation_date TEXT NOT NULL,
                meal_name TEXT NOT NULL,
                quantity_prepared REAL NOT NULL CHECK(quantity_prepared >= 0),
                quantity_consumed REAL NOT NULL CHECK(quantity_consumed >= 0),
                notes TEXT,
                created_by TEXT NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                supersedes_id TEXT REFERENCES production_observations(id),
                correction_reason TEXT
            );
            CREATE TABLE IF NOT EXISTS observation_audit_events (
                id TEXT PRIMARY KEY,
                observation_id TEXT NOT NULL REFERENCES production_observations(id),
                actor_id TEXT NOT NULL REFERENCES users(id),
                event_type TEXT NOT NULL,
                event_at TEXT NOT NULL,
                details TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_safety_batch ON safety_verifications(batch_id);
            CREATE INDEX IF NOT EXISTS idx_assignments_batch ON assignments(batch_id);
            CREATE INDEX IF NOT EXISTS idx_audit_batch ON audit_events(batch_id, event_at);
            CREATE INDEX IF NOT EXISTS idx_observations_date_meal
                ON production_observations(observation_date, meal_name);
            CREATE INDEX IF NOT EXISTS idx_observation_audit_observation
                ON observation_audit_events(observation_id, event_at);
            """
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(auth_events)").fetchall()
        }
        if "actor_id" not in columns:
            connection.execute("ALTER TABLE auth_events ADD COLUMN actor_id TEXT")
        audit_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(audit_events)").fetchall()
        }
        if "actor_id" not in audit_columns:
            connection.execute("ALTER TABLE audit_events ADD COLUMN actor_id TEXT")
        observation_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(production_observations)"
            ).fetchall()
        }
        if "supersedes_id" not in observation_columns:
            connection.execute(
                "ALTER TABLE production_observations "
                "ADD COLUMN supersedes_id TEXT REFERENCES production_observations(id)"
            )
        if "correction_reason" not in observation_columns:
            connection.execute(
                "ALTER TABLE production_observations ADD COLUMN correction_reason TEXT"
            )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_observations_supersedes "
            "ON production_observations(supersedes_id)"
        )


def get_connection() -> sqlite3.Connection:
    initialize_database()
    return _open_connection()
