"""Authentication helpers for pre-provisioned application users."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import Cookie, HTTPException

USERS_FILE = Path(os.environ.get("USERS_FILE", Path(__file__).with_name("users.json")))
PASSWORD_ITERATIONS = 600_000
SESSION_DURATION_SECONDS = 12 * 60 * 60
ROLES = {"student", "parent", "staff", "admin"}
_sessions: dict[str, tuple[str, float]] = {}


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Passwords must be at least 12 characters long")

    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return "$".join(
        (
            "pbkdf2_sha256",
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(password_hash).decode("ascii"),
        )
    )


def _parse_password_hash(encoded_hash: str) -> tuple[int, bytes, bytes]:
    algorithm, iterations, encoded_salt, encoded_digest = encoded_hash.split("$")
    if algorithm != "pbkdf2_sha256":
        raise ValueError("Unsupported password hash algorithm")

    iteration_count = int(iterations)
    if not 100_000 <= iteration_count <= 1_000_000:
        raise ValueError("Invalid password hash iteration count")
    salt = base64.urlsafe_b64decode(encoded_salt.encode("ascii"))
    expected_digest = base64.urlsafe_b64decode(encoded_digest.encode("ascii"))
    if len(salt) < 16 or len(expected_digest) != 32:
        raise ValueError("Invalid password hash")
    return iteration_count, salt, expected_digest


def verify_password(password: str, encoded_hash: str) -> bool:
    iteration_count, salt, expected_digest = _parse_password_hash(encoded_hash)
    actual_digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iteration_count
    )
    return hmac.compare_digest(actual_digest, expected_digest)


def load_users() -> list[dict[str, str]]:
    try:
        data: Any = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RuntimeError(
            f"User store not found at {USERS_FILE}; create it with manage_users.py"
        ) from error
    except json.JSONDecodeError as error:
        raise RuntimeError(f"User store at {USERS_FILE} is not valid JSON") from error

    if not isinstance(data, dict) or not isinstance(data.get("users"), list):
        raise RuntimeError("User store must contain a 'users' array")

    users = data["users"]
    usernames: set[str] = set()
    emails: set[str] = set()
    for user in users:
        if not isinstance(user, dict) or not all(
            isinstance(user.get(key), str)
            for key in ("username", "email", "role", "password_hash")
        ):
            raise RuntimeError("Each user must have username, email, role, and password_hash")
        username = user["username"].casefold()
        email = user["email"].casefold()
        if not username or username in usernames:
            raise RuntimeError("Usernames must be non-empty and unique")
        if not email or email in emails:
            raise RuntimeError("Email addresses must be non-empty and unique")
        if user["role"] not in ROLES:
            raise RuntimeError(f"Invalid role for user {user['username']}")
        try:
            _parse_password_hash(user["password_hash"])
        except (TypeError, ValueError, UnicodeError) as error:
            raise RuntimeError(f"Invalid password hash for user {user['username']}") from error
        usernames.add(username)
        emails.add(email)

    return users


def find_user(username: str) -> dict[str, str] | None:
    normalized_username = username.casefold()
    return next(
        (
            user
            for user in load_users()
            if user["username"].casefold() == normalized_username
        ),
        None,
    )


def authenticate(username: str, password: str) -> dict[str, str] | None:
    user = find_user(username)
    if user is None:
        # Perform a password hash even for unknown usernames to reduce timing leaks.
        dummy_hash = (
            "pbkdf2_sha256$600000$"
            "MDEyMzQ1Njc4OWFiY2RlZg==$"
            "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        )
        verify_password(password, dummy_hash)
        return None

    if not verify_password(password, user["password_hash"]):
        return None
    return user


def public_user(user: dict[str, str]) -> dict[str, str]:
    return {key: user[key] for key in ("username", "email", "role")}


def create_session(username: str) -> str:
    now = time.time()
    expired_tokens = [
        token for token, (_, expires_at) in _sessions.items() if expires_at <= now
    ]
    for token in expired_tokens:
        delete_session(token)

    token = secrets.token_urlsafe(32)
    _sessions[token] = (username, now + SESSION_DURATION_SECONDS)
    return token


def delete_session(token: str | None) -> None:
    if token is not None:
        _sessions.pop(token, None)


def current_user(session_token: str | None) -> dict[str, str]:
    if session_token is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    session = _sessions.get(session_token)
    if session is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    username, expires_at = session
    if expires_at <= time.time():
        delete_session(session_token)
        raise HTTPException(status_code=401, detail="Session expired")

    user = find_user(username)
    if user is None:
        delete_session(session_token)
        raise HTTPException(status_code=401, detail="Authentication required")
    return public_user(user)


def require_role(*allowed_roles: str):
    def role_dependency(
        session_token: str | None = Cookie(default=None, alias="session"),
    ) -> dict[str, str]:
        user = current_user(session_token)
        if user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="You are not allowed to perform this action")
        return user

    return role_dependency


def get_current_user(
    session_token: str | None = Cookie(default=None, alias="session"),
) -> dict[str, str]:
    return current_user(session_token)
