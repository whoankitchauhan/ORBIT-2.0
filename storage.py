"""SQLite persistence for simulated cases, workflow state, and audit history."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from dotenv import load_dotenv

from sample_data import POLICIES, SHIPMENTS

load_dotenv()

PROJECT_DIR = Path(__file__).resolve().parent


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def get_db_path(db_path: str | Path | None = None) -> Path:
    configured_path = db_path if db_path is not None else os.getenv("ORBIT_DB_PATH", "orbit_data.db")
    path = Path(configured_path).expanduser()
    return path if path.is_absolute() else PROJECT_DIR / path


@contextmanager
def connect(db_path: str | Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    path = get_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database(db_path: str | Path | None = None) -> None:
    with connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS shipments (
                shipment_id TEXT PRIMARY KEY,
                record_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS policies (
                claim_type TEXT PRIMARY KEY,
                policy_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                shipment_id TEXT NOT NULL REFERENCES shipments(shipment_id),
                owner_email TEXT,
                complaint TEXT NOT NULL,
                status TEXT NOT NULL,
                decision TEXT,
                recommendation TEXT,
                action_type TEXT,
                action_status TEXT,
                approval_status TEXT,
                requires_approval INTEGER NOT NULL DEFAULT 0,
                processing_ms INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                state_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS agent_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                agent TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approvals (
                approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE REFERENCES runs(run_id),
                status TEXT NOT NULL,
                reviewer TEXT,
                note TEXT,
                requested_at TEXT NOT NULL,
                decided_at TEXT
            );
            CREATE TABLE IF NOT EXISTS actions (
                action_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE REFERENCES runs(run_id),
                action_type TEXT NOT NULL,
                requires_approval INTEGER NOT NULL,
                status TEXT NOT NULL,
                simulation INTEGER NOT NULL DEFAULT 1,
                result TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_entries (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(run_id),
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                details_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_agent_events_run_id ON agent_events(run_id, event_id);
            CREATE INDEX IF NOT EXISTS idx_audit_entries_run_id ON audit_entries(run_id, audit_id);
            """
        )
        run_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(runs)").fetchall()
        }
        if "owner_email" not in run_columns:
            connection.execute("ALTER TABLE runs ADD COLUMN owner_email TEXT")
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_runs_owner_created_at
            ON runs(owner_email, created_at DESC)
            """
        )
        connection.executemany(
            "INSERT OR IGNORE INTO shipments (shipment_id, record_json) VALUES (?, ?)",
            [
                (shipment["shipment_id"], json.dumps(shipment, sort_keys=True))
                for shipment in SHIPMENTS
            ],
        )
        connection.executemany(
            "INSERT OR IGNORE INTO policies (claim_type, policy_json) VALUES (?, ?)",
            [
                (policy["claim_type"], json.dumps(policy, sort_keys=True))
                for policy in POLICIES
            ],
        )


def list_shipments(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT record_json FROM shipments ORDER BY shipment_id"
        ).fetchall()
    return [json.loads(row["record_json"]) for row in rows]


def get_shipment(shipment_id: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT record_json FROM shipments WHERE shipment_id = ?",
            (shipment_id,),
        ).fetchone()
    return json.loads(row["record_json"]) if row else None


def get_policy(claim_type: str, db_path: str | Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT policy_json FROM policies WHERE claim_type = ?",
            (claim_type,),
        ).fetchone()
    return json.loads(row["policy_json"]) if row else None


def list_policies(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with connect(db_path) as connection:
        rows = connection.execute(
            "SELECT policy_json FROM policies ORDER BY claim_type"
        ).fetchall()
    return [json.loads(row["policy_json"]) for row in rows]


def list_runs(
    db_path: str | Path | None = None,
    limit: int = 50,
    owner_email: str | None = None,
    is_admin: bool = False,
) -> list[dict[str, Any]]:
    query = """
        SELECT run_id, shipment_id, owner_email, complaint, status, decision, action_type,
               action_status, approval_status, processing_ms, error, created_at
        FROM runs
    """
    parameters: tuple[Any, ...]
    if owner_email is not None and not is_admin:
        query += " WHERE owner_email = ?"
        parameters = (owner_email.strip().lower(), limit)
    else:
        parameters = (limit,)
    query += " ORDER BY created_at DESC LIMIT ?"
    with connect(db_path) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [dict(row) for row in rows]


def get_run_details(
    run_id: str,
    db_path: str | Path | None = None,
    owner_email: str | None = None,
    is_admin: bool = False,
) -> dict[str, Any] | None:
    with connect(db_path) as connection:
        run_row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if run_row is None or (
            owner_email is not None
            and not is_admin
            and run_row["owner_email"] != owner_email.strip().lower()
        ):
            return None
        events = connection.execute(
            "SELECT * FROM agent_events WHERE run_id = ? ORDER BY event_id",
            (run_id,),
        ).fetchall()
        approval = connection.execute(
            "SELECT * FROM approvals WHERE run_id = ?", (run_id,)
        ).fetchone()
        action = connection.execute(
            "SELECT * FROM actions WHERE run_id = ?", (run_id,)
        ).fetchone()
        audit = connection.execute(
            "SELECT * FROM audit_entries WHERE run_id = ? ORDER BY audit_id",
            (run_id,),
        ).fetchall()

    run = dict(run_row)
    run["state"] = json.loads(run.pop("state_json"))
    run["events"] = [
        {**dict(event), "details": json.loads(event["details_json"])}
        for event in events
    ]
    run["approval"] = dict(approval) if approval else None
    run["action"] = dict(action) if action else None
    run["audit"] = [
        {**dict(entry), "details": json.loads(entry["details_json"])}
        for entry in audit
    ]
    return run
