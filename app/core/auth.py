import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from secrets import compare_digest
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash

from app.core.config import (
    INSECURE_SECRET_PLACEHOLDER,
    settings,
    validate_security_configuration,
)
from app.db.database import get_connection


class Role(StrEnum):
    ADMIN = "ADMIN"
    KITCHEN_OPERATOR = "KITCHEN_OPERATOR"
    FOOD_SAFETY_VERIFIER = "FOOD_SAFETY_VERIFIER"
    AUDITOR = "AUDITOR"


PERMISSIONS: dict[str, frozenset[Role]] = {
    "forecast": frozenset({Role.ADMIN, Role.KITCHEN_OPERATOR, Role.AUDITOR}),
    "surplus_read": frozenset(set(Role)),
    "surplus_write": frozenset({Role.ADMIN, Role.KITCHEN_OPERATOR}),
    "batch_read": frozenset(set(Role)),
    "batch_create": frozenset({Role.ADMIN, Role.KITCHEN_OPERATOR}),
    "verification": frozenset({Role.ADMIN, Role.FOOD_SAFETY_VERIFIER}),
    "recipient_read": frozenset(set(Role)),
    "recipient_write": frozenset({Role.ADMIN, Role.KITCHEN_OPERATOR}),
    "assignment": frozenset({Role.ADMIN, Role.KITCHEN_OPERATOR}),
    "delivery_disposal": frozenset({Role.ADMIN, Role.KITCHEN_OPERATOR}),
    "audit_read": frozenset({Role.ADMIN, Role.AUDITOR}),
    "user_admin": frozenset({Role.ADMIN}),
    "observation_read": frozenset(set(Role)),
    "observation_write": frozenset({Role.ADMIN, Role.KITCHEN_OPERATOR}),
}

PASSWORD_HASH = PasswordHash.recommended()
BEARER = HTTPBearer(auto_error=False)
LOGIN_FAILURE_LIMIT = 5
LOGIN_FAILURE_WINDOW_SECONDS = 60.0
_login_attempts: dict[str, list[float]] = {}
_login_attempts_lock = threading.Lock()


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    username: str
    role: Role
    active: bool = True


def _normalize_username(username: str) -> str:
    normalized = username.strip().casefold()
    if len(normalized) < 3 or len(normalized) > 254 or " " in normalized:
        raise ValueError("username must be 3-254 characters without spaces.")
    return normalized


def _validate_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 12 or len(password) > 256:
        raise ValueError("password must be 12-256 characters.")
    return password


def _require_secret() -> str:
    secret = settings.auth_secret_key
    if (
        not secret
        or secret == INSECURE_SECRET_PLACEHOLDER
        or len(secret) < 32
    ):
        raise RuntimeError("FOODLOOP_AUTH_SECRET_KEY must be a random value of at least 32 characters.")
    return secret


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_user(row) -> AuthenticatedUser:
    return AuthenticatedUser(row["id"], row["username"], Role(row["role"]), bool(row["active"]))


def create_user(
    username: str,
    password: str,
    role: Role,
    active: bool = True,
    actor_id: str | None = None,
) -> dict:
    if actor_id is not None:
        authorize_actor(actor_id, "user_admin")
    else:
        with get_connection() as connection:
            admin_exists = connection.execute(
                "SELECT 1 FROM users WHERE role = ?", (Role.ADMIN.value,)
            ).fetchone()
        if admin_exists is not None or role != Role.ADMIN:
            raise ValueError("authenticated actor is required.")
    normalized = _normalize_username(username)
    password = _validate_password(password)
    if not isinstance(role, Role):
        role = Role(role)
    user_id = str(uuid4())
    timestamp = _now()
    with get_connection() as connection:
        try:
            connection.execute(
                """
                INSERT INTO users (id, username, password_hash, role, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, normalized, PASSWORD_HASH.hash(password), role.value, int(active), timestamp, timestamp),
            )
        except sqlite3.IntegrityError as error:
            if "UNIQUE constraint failed: users.username" in str(error):
                raise ValueError("username is already registered.") from error
            raise
        connection.execute(
            "INSERT INTO auth_events (id, user_id, actor_id, event_type, event_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid4()), user_id, actor_id, "user_created", timestamp),
        )
        return {"id": user_id, "username": normalized, "role": role.value, "active": active}


def set_user_active(user_id: str, active: bool, actor_id: str) -> dict:
    authorize_actor(actor_id, "user_admin")
    if user_id == actor_id and not active:
        raise ValueError("an administrator cannot deactivate their own account.")
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE users SET active = ?, updated_at = ? WHERE id = ?",
            (int(active), _now(), user_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("user was not found.")
        connection.execute(
            "INSERT INTO auth_events (id, user_id, actor_id, event_type, event_at, details) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid4()), user_id, actor_id, "user_status_changed", _now(), f"target_user_id={user_id};active={active}"),
        )
        row = connection.execute(
            "SELECT id, username, role, active FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row)


def set_user_role(user_id: str, role: Role, actor_id: str) -> dict:
    authorize_actor(actor_id, "user_admin")
    if not isinstance(role, Role):
        role = Role(role)
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE users SET role = ?, updated_at = ? WHERE id = ?",
            (role.value, _now(), user_id),
        )
        if cursor.rowcount != 1:
            raise ValueError("user was not found.")
        connection.execute(
            """
            INSERT INTO auth_events
            (id, user_id, actor_id, event_type, event_at, details)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                user_id,
                actor_id,
                "user_role_changed",
                _now(),
                f"role={role.value}",
            ),
        )
        row = connection.execute(
            "SELECT id, username, role, active FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row)


def list_users() -> list[dict]:
    with get_connection() as connection:
        return [dict(row) for row in connection.execute(
            "SELECT id, username, role, active, created_at, updated_at FROM users ORDER BY username"
        ).fetchall()]


def authenticate(username: str, password: str) -> AuthenticatedUser | None:
    try:
        normalized = _normalize_username(username)
    except ValueError:
        return None
    with get_connection() as connection:
        row = connection.execute(
            "SELECT * FROM users WHERE username = ?", (normalized,)
        ).fetchone()
        if row is None:
            return None
        try:
            valid = PASSWORD_HASH.verify(password, row["password_hash"])
        except (ValueError, TypeError):
            valid = False
        if not valid or not row["active"]:
            event = "login_failed" if not valid else "login_disabled"
            connection.execute(
                "INSERT INTO auth_events (id, user_id, event_type, event_at) VALUES (?, ?, ?, ?)",
                (str(uuid4()), row["id"], event, _now()),
            )
            return None
        connection.execute(
            "INSERT INTO auth_events (id, user_id, event_type, event_at) VALUES (?, ?, ?, ?)",
            (str(uuid4()), row["id"], "login_succeeded", _now()),
        )
        return _row_to_user(row)


def check_login_rate_limit(username: str) -> int | None:
    try:
        key = _normalize_username(username)
    except ValueError:
        key = username.strip().casefold()
    now = time.monotonic()
    with _login_attempts_lock:
        _login_attempts_copy = {
            stored_key: timestamps
            for stored_key, timestamps in _login_attempts.items()
            if timestamps and now - timestamps[-1] < LOGIN_FAILURE_WINDOW_SECONDS
        }
        _login_attempts.clear()
        _login_attempts.update(_login_attempts_copy)
        attempts = [
            timestamp
            for timestamp in _login_attempts.get(key, [])
            if now - timestamp < LOGIN_FAILURE_WINDOW_SECONDS
        ]
        _login_attempts[key] = attempts
        if len(attempts) < LOGIN_FAILURE_LIMIT:
            return None
        return max(1, int(LOGIN_FAILURE_WINDOW_SECONDS - (now - attempts[0])))


def record_login_failure(username: str) -> None:
    try:
        key = _normalize_username(username)
    except ValueError:
        key = username.strip().casefold()
    now = time.monotonic()
    with _login_attempts_lock:
        attempts = [
            timestamp
            for timestamp in _login_attempts.get(key, [])
            if now - timestamp < LOGIN_FAILURE_WINDOW_SECONDS
        ]
        attempts.append(now)
        _login_attempts[key] = attempts[-LOGIN_FAILURE_LIMIT:]


def clear_login_failures(username: str) -> None:
    try:
        key = _normalize_username(username)
    except ValueError:
        key = username.strip().casefold()
    with _login_attempts_lock:
        _login_attempts.pop(key, None)


def issue_token(user: AuthenticatedUser) -> str:
    secret = _require_secret()
    issued = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "iat": issued,
        "exp": issued + timedelta(minutes=settings.auth_token_minutes),
        "jti": str(uuid4()),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def user_from_token(token: str) -> AuthenticatedUser:
    try:
        payload = jwt.decode(token, _require_secret(), algorithms=["HS256"], options={"require": ["sub", "iat", "exp", "jti"]})
        user_id = payload["sub"]
    except (jwt.InvalidTokenError, RuntimeError, KeyError, TypeError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, username, role, active FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if row is None or not row["active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _row_to_user(row)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(BEARER)) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_from_token(credentials.credentials)


def require_permission(permission: str):
    allowed = PERMISSIONS[permission]

    def dependency(user: AuthenticatedUser = Depends(current_user)) -> AuthenticatedUser:
        if user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions.")
        return user

    return dependency


def authorize_actor(actor_id: str | None, permission: str) -> AuthenticatedUser:
    if not actor_id:
        raise ValueError("authenticated actor is required.")
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, username, role, active FROM users WHERE id = ?", (actor_id,)
        ).fetchone()
    if row is None or not row["active"]:
        raise ValueError("authenticated actor is invalid or inactive.")
    user = _row_to_user(row)
    if user.role not in PERMISSIONS[permission]:
        raise ValueError("authenticated actor lacks permission.")
    return user


def bootstrap_admin(username: str, password: str) -> dict:
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT 1 FROM users WHERE role = ?", (Role.ADMIN.value,)
        ).fetchone()
    if existing is not None:
        raise ValueError("an administrator already exists; bootstrap is one-time.")
    return create_user(username, password, Role.ADMIN)


def safe_equal(left: str, right: str) -> bool:
    return compare_digest(left, right)
