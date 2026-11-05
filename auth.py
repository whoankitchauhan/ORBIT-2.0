"""Local account storage and role checks for the ORBIT demo."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from dotenv import load_dotenv

load_dotenv()

PROJECT_DIR = Path(__file__).resolve().parent
PASSWORD_ITERATIONS = 240_000
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def get_auth_db_path(db_path: str | Path | None = None) -> Path:
    configured_path = (
        db_path if db_path is not None
        else os.getenv("ORBIT_AUTH_DB_PATH", "orbit_users.db")
    )
    path = Path(configured_path).expanduser()
    return path if path.is_absolute() else PROJECT_DIR / path


@contextmanager
def _connect(db_path: str | Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    path = get_auth_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_auth_database(db_path: str | Path | None = None) -> None:
    with _connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                role TEXT NOT NULL DEFAULT 'user'
                    CHECK (role IN ('admin', 'user'))
            )
            """
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        if "role" not in columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'"
            )
        connection.execute(
            """
            UPDATE users SET role = 'user'
            WHERE role IS NULL OR role NOT IN ('admin', 'user')
            """
        )


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _validate_account(email: str, password: str) -> str | None:
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        return "Enter a valid email address."
    if not 8 <= len(password) <= 1024:
        return "Use a password with between 8 and 1,024 characters."
    return None


def _password_hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )


def register_user(
    email: str,
    password: str,
    db_path: str | Path | None = None,
) -> tuple[bool, str]:
    normalized_email = normalize_email(email)
    error = _validate_account(normalized_email, password)
    if error:
        return False, error

    salt = os.urandom(16)
    initialize_auth_database(db_path)
    try:
        with _connect(db_path) as connection:
            connection.execute(
                """
                INSERT INTO users (email, salt, password_hash, role)
                VALUES (?, ?, ?, 'user')
                """,
                (normalized_email, salt, _password_hash(password, salt)),
            )
    except sqlite3.IntegrityError:
        return False, "An account with this email already exists."
    return True, "Account created with User access. An administrator can promote it."


def get_user(email: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    initialize_auth_database(db_path)
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT email, role, created_at FROM users WHERE email = ?",
            (normalize_email(email),),
        ).fetchone()
    return dict(row) if row else None


def authenticate_user(
    email: str,
    password: str,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    initialize_auth_database(db_path)
    with _connect(db_path) as connection:
        row = connection.execute(
            "SELECT email, salt, password_hash, role, created_at FROM users WHERE email = ?",
            (normalize_email(email),),
        ).fetchone()
    if row is None or not hmac.compare_digest(
        _password_hash(password, row["salt"]), row["password_hash"]
    ):
        return None
    return {
        "email": row["email"],
        "role": row["role"],
        "created_at": row["created_at"],
    }


def require_admin(email: str, db_path: str | Path | None = None) -> dict[str, Any]:
    user = get_user(email, db_path)
    if user is None or user["role"] != "admin":
        raise PermissionError("Administrator access is required for this action.")
    return user


def promote_user_to_admin(email: str, db_path: str | Path | None = None) -> None:
    normalized_email = normalize_email(email)
    initialize_auth_database(db_path)
    with _connect(db_path) as connection:
        result = connection.execute(
            "UPDATE users SET role = 'admin' WHERE email = ?",
            (normalized_email,),
        )
        if result.rowcount != 1:
            raise ValueError(
                f"No account exists for {normalized_email}. Create it in ORBIT first."
            )


def _run_cli(arguments: list[str]) -> int:
    if len(arguments) != 2 or arguments[0] != "promote-admin":
        print("Usage: python auth.py promote-admin <registered-email>")
        return 2

    email = normalize_email(arguments[1])
    try:
        promote_user_to_admin(email)
    except ValueError as error:
        print(error)
        return 1
    print(f"{email} now has Administrator access.")
    print("Sign out and sign in again to refresh the role in an open browser session.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_run_cli(sys.argv[1:]))
