"""Supervisor workflow and guarded, simulation-only claim actions."""

from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from agents import action_agent, analysis_agent, research_agent, validation_agent
from auth import require_admin
from storage import connect, get_policy, get_run_details, get_shipment, initialize_database, utc_now
from orbit_intelligence import adaptive_plan, build_debate, uncertainty_assessment, decision_graph

FaultInjector = Callable[[str], None]


class WorkflowError(RuntimeError):
    """An agent failure that was persisted and can be resumed by run ID."""

    def __init__(self, run_id: str, message: str):
        super().__init__(message)
        self.run_id = run_id


def _insert_audit(
    connection: sqlite3.Connection,
    run_id: str,
    event_type: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO audit_entries (run_id, event_type, message, details_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (run_id, event_type, message, json.dumps(details or {}, sort_keys=True), utc_now()),
    )


def run_claim_workflow(
    run_id: str,
    db_path: str | Path | None = None,
    fault_injector: FaultInjector | None = None,
    owner_email: str | None = None,
    is_admin: bool = False,
) -> dict[str, Any]:
    """Continue an interrupted run, skipping agent stages already persisted."""
    initialize_database(db_path)
    run = get_run_details(
        run_id, db_path, owner_email=owner_email, is_admin=is_admin
    )
    if run is None:
        raise ValueError(f"Unknown workflow run: {run_id}")
    if run["status"] not in {"processing", "failed"}:
        raise ValueError(f"Run {run_id} cannot be resumed from status '{run['status']}'.")

    shipment = get_shipment(run["shipment_id"], db_path)
    policy = get_policy(shipment["claim_type"], db_path) if shipment else None
    if shipment is None or policy is None:
        raise ValueError("The simulated shipment or its claim policy is missing.")

    if run["status"] == "failed":
        with connect(db_path) as connection:
            connection.execute(
                "UPDATE runs SET status = 'processing', error = NULL WHERE run_id = ?",
                (run_id,),
            )
            _insert_audit(connection, run_id, "workflow_resumed", "Retrying from the last persisted agent result.")

    state: dict[str, Any] = run["state"]
    complaint = run["complaint"]
    stages: tuple[tuple[str, str, Callable[..., dict[str, Any]], tuple[Any, ...]], ...] = (
        ("research", "Research Agent", research_agent, (shipment, complaint, policy)),
        ("analysis", "Analysis Agent", analysis_agent, ()),
        ("validation", "Validation Agent", validation_agent, ()),
        ("action", "Action Agent", action_agent, ()),
    )
    started = time.perf_counter()
    for stage_name, agent_name, agent, arguments in stages:
        if stage_name in state:
            continue
        event_time = utc_now()
        with connect(db_path) as connection:
            event_cursor = connection.execute(
                """
                INSERT INTO agent_events (run_id, agent, status, message, created_at)
                VALUES (?, ?, 'running', ?, ?)
                """,
                (run_id, agent_name, f"{agent_name} started.", event_time),
            )
            event_id = event_cursor.lastrowid
        try:
            if fault_injector is not None:
                fault_injector(stage_name)
            if stage_name == "analysis":
                result = agent(state["research"])
            elif stage_name == "validation":
                result = agent(state["research"], state["analysis"])
            elif stage_name == "action":
                result = agent(state["analysis"], state["validation"])
            else:
                result = agent(*arguments)
        except Exception as error:
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            with connect(db_path) as connection:
                connection.execute(
                    """
                    UPDATE agent_events SET status = 'failed', message = ?, details_json = ?
                    WHERE event_id = ?
                    """,
                    (f"{agent_name} failed: {error}", json.dumps({"error": str(error)}), event_id),
                )
                connection.execute(
                    """
                    UPDATE runs
                    SET status = 'failed', error = ?, processing_ms = processing_ms + ?
                    WHERE run_id = ?
                    """,
                    (f"{agent_name} failed: {error}", elapsed_ms, run_id),
                )
                _insert_audit(
                    connection,
                    run_id,
                    "agent_failed",
                    f"{agent_name} failed; its error and completed prior stages were saved.",
                    {"agent": agent_name, "error": str(error)},
                )
            raise WorkflowError(run_id, f"{agent_name} failed: {error}") from error

        state[stage_name] = result
        details = result if stage_name in {"research", "analysis", "validation"} else {
            "action_type": result["action_type"],
            "requires_approval": result["requires_approval"],
            "description": result["description"],
        }
        with connect(db_path) as connection:
            connection.execute(
                """
                UPDATE agent_events SET status = 'completed', message = ?, details_json = ?
                WHERE event_id = ?
                """,
                (
                    f"{agent_name} completed.",
                    json.dumps(details, sort_keys=True),
                    event_id,
                ),
            )
            connection.execute(
                "UPDATE runs SET state_json = ? WHERE run_id = ?",
                (json.dumps(state, sort_keys=True), run_id),
            )
            _insert_audit(
                connection,
                run_id,
                "agent_completed",
                f"{agent_name} completed and its result was persisted.",
                {"agent": agent_name},
            )

    # ORBIT explainability layer: derived only from persisted agent outputs.
    if "adaptive_plan" not in state:
        state["adaptive_plan"] = adaptive_plan(shipment, complaint, policy)
        state["debate"] = build_debate(state["research"], state["analysis"], state["validation"])
        state["uncertainty"] = uncertainty_assessment(
            state["research"], state["analysis"], state["validation"], state["debate"]
        )
        state["decision_graph"] = decision_graph(state)
        with connect(db_path) as connection:
            connection.execute("UPDATE runs SET state_json = ? WHERE run_id = ?",
                               (json.dumps(state, sort_keys=True), run_id))
            _insert_audit(connection, run_id, "intelligence_assessed",
                          "Adaptive plan, bounded debate, uncertainty assessment and decision graph persisted.",
                          {"complexity": state["adaptive_plan"]["complexity"],
                           "support_score": state["uncertainty"]["decision_support_score"],
                           "route": state["uncertainty"]["route"]})

    action = state["action"]
    decision = state["analysis"]["decision"]
    approval_status = "pending" if action["requires_approval"] else "not_required"
    action_status = action["status"]
    final_status = "awaiting_approval" if action["requires_approval"] else "completed"
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    state["execution_notice"] = (
        "Simulation only. No Delhivery shipment, refund, support ticket, or external system was changed."
    )
    with connect(db_path) as connection:
        connection.execute(
            """
            UPDATE runs
            SET status = ?, decision = ?, recommendation = ?, action_type = ?,
                action_status = ?, approval_status = ?, requires_approval = ?,
                processing_ms = processing_ms + ?, state_json = ?, error = NULL, completed_at = ?
            WHERE run_id = ?
            """,
            (
                final_status,
                decision,
                state["analysis"]["recommendation"],
                action["action_type"],
                action_status,
                approval_status,
                int(action["requires_approval"]),
                elapsed_ms,
                json.dumps(state, sort_keys=True),
                utc_now(),
                run_id,
            ),
        )
        connection.execute(
            """
            INSERT INTO actions
                (run_id, action_type, requires_approval, status, simulation, result, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                run_id,
                action["action_type"],
                int(action["requires_approval"]),
                action_status,
                action["description"],
                utc_now(),
                utc_now(),
            ),
        )
        connection.execute(
            """
            INSERT INTO approvals (run_id, status, requested_at)
            VALUES (?, ?, ?)
            """,
            (run_id, approval_status, utc_now()),
        )
        _insert_audit(
            connection,
            run_id,
            "action_prepared",
            action["description"],
            {
                "action_type": action["action_type"],
                "requires_approval": action["requires_approval"],
                "simulation": True,
            },
        )
        _insert_audit(
            connection,
            run_id,
            "workflow_completed",
            f"Supervisor completed with decision '{decision}'.",
            {"decision": decision, "status": final_status},
        )
    completed_run = get_run_details(
        run_id, db_path, owner_email=owner_email, is_admin=is_admin
    )
    if completed_run is None:
        raise RuntimeError(f"Run {run_id} was persisted but could not be reloaded.")
    return completed_run


def resume_claim_workflow(
    run_id: str,
    db_path: str | Path | None = None,
    owner_email: str | None = None,
    is_admin: bool = False,
) -> dict[str, Any]:
    """Retry a failed workflow using its last persisted agent results."""
    return run_claim_workflow(
        run_id, db_path, owner_email=owner_email, is_admin=is_admin
    )


def start_claim_workflow(
    shipment_id: str,
    complaint: str,
    db_path: str | Path | None = None,
    fault_injector: FaultInjector | None = None,
    owner_email: str | None = None,
) -> dict[str, Any]:
    """Validate and persist a complaint, then run the supervisor's agents."""
    normalized_id = shipment_id.strip().upper()
    normalized_complaint = complaint.strip()
    if not re.fullmatch(r"DLV-\d{4}", normalized_id):
        raise ValueError("Shipment ID must use the DLV-0000 format.")
    if not 10 <= len(normalized_complaint) <= 1000:
        raise ValueError("Complaint must contain between 10 and 1,000 characters.")
    initialize_database(db_path)
    shipment = get_shipment(normalized_id, db_path)
    if shipment is None:
        raise ValueError(f"No simulated shipment record exists for {normalized_id}.")

    run_id = str(uuid.uuid4())
    now = utc_now()
    with connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO runs (
                run_id, shipment_id, owner_email, complaint, status, created_at
            )
            VALUES (?, ?, ?, ?, 'processing', ?)
            """,
            (
                run_id,
                normalized_id,
                owner_email.strip().lower() if owner_email else None,
                normalized_complaint,
                now,
            ),
        )
        _insert_audit(
            connection,
            run_id,
            "workflow_started",
            "Supervisor accepted a validated complaint against the local simulated case file.",
            {"shipment_id": normalized_id},
        )
    try:
        return run_claim_workflow(
            run_id, db_path, fault_injector, owner_email=owner_email
        )
    except WorkflowError:
        raise
    except Exception as error:
        with connect(db_path) as connection:
            connection.execute(
                "UPDATE runs SET status = 'failed', error = ? WHERE run_id = ?",
                (str(error), run_id),
            )
            _insert_audit(connection, run_id, "workflow_failed", str(error))
        raise WorkflowError(run_id, f"Workflow failed: {error}") from error


def _execute_simulated_action(
    connection: sqlite3.Connection,
    run_id: str,
) -> None:
    action = connection.execute(
        "SELECT * FROM actions WHERE run_id = ?", (run_id,)
    ).fetchone()
    approval = connection.execute(
        "SELECT * FROM approvals WHERE run_id = ?", (run_id,)
    ).fetchone()
    if action is None or approval is None:
        raise ValueError("Action or approval record is missing.")
    if not action["requires_approval"] or approval["status"] != "approved":
        raise PermissionError("This simulated action is blocked until its required human approval is recorded.")
    if action["status"] != "awaiting_approval":
        raise ValueError(f"Action cannot execute from status '{action['status']}'.")

    result = (
        "Simulated execution recorded after human approval. "
        "No Delhivery system, shipment, refund, or support ticket was changed."
    )
    now = utc_now()
    connection.execute(
        "UPDATE actions SET status = 'simulated_executed', result = ?, updated_at = ? WHERE run_id = ?",
        (result, now, run_id),
    )
    connection.execute(
        "UPDATE runs SET status = 'completed', action_status = 'simulated_executed' WHERE run_id = ?",
        (run_id,),
    )
    _insert_audit(
        connection,
        run_id,
        "simulated_action_executed",
        result,
        {"action_type": action["action_type"], "simulation": True},
    )


def execute_simulated_action(run_id: str, db_path: str | Path | None = None) -> dict[str, Any]:
    """Execute only a sensitive action whose approved status is already persisted."""
    initialize_database(db_path)
    with connect(db_path) as connection:
        _execute_simulated_action(connection, run_id)
    run = get_run_details(run_id, db_path)
    if run is None:
        raise RuntimeError(f"Run {run_id} was updated but could not be reloaded.")
    return run


def decide_approval(
    run_id: str,
    decision: str,
    reviewer: str,
    note: str = "",
    db_path: str | Path | None = None,
    auth_db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Record an administrator decision and execute an approved action in simulation only."""
    administrator = require_admin(reviewer, auth_db_path)
    normalized_decision = decision.strip().lower()
    normalized_reviewer = administrator["email"]
    if normalized_decision not in {"approved", "rejected"}:
        raise ValueError("Approval decision must be 'approved' or 'rejected'.")
    if not normalized_reviewer or len(normalized_reviewer) > 254:
        raise ValueError("Administrator email must contain between 1 and 254 characters.")
    initialize_database(db_path)
    with connect(db_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        run = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        approval = connection.execute(
            "SELECT * FROM approvals WHERE run_id = ?", (run_id,)
        ).fetchone()
        action = connection.execute(
            "SELECT * FROM actions WHERE run_id = ?", (run_id,)
        ).fetchone()
        if run is None or approval is None or action is None:
            raise ValueError("A pending workflow action and approval record are required.")
        if run["status"] != "awaiting_approval" or approval["status"] != "pending":
            raise ValueError("This workflow has no pending approval.")
        if not action["requires_approval"]:
            raise PermissionError("This action is not eligible for this approval flow.")

        decided_at = utc_now()
        connection.execute(
            """
            UPDATE approvals SET status = ?, reviewer = ?, note = ?, decided_at = ?
            WHERE run_id = ?
            """,
            (normalized_decision, normalized_reviewer, note.strip(), decided_at, run_id),
        )
        if normalized_decision == "approved":
            connection.execute(
                "UPDATE runs SET approval_status = 'approved' WHERE run_id = ?",
                (run_id,),
            )
            _insert_audit(
                connection,
                run_id,
                "approval_granted",
                "Human reviewer approved the action for simulated execution.",
                {"reviewer": normalized_reviewer, "note": note.strip()},
            )
            _execute_simulated_action(connection, run_id)
        else:
            connection.execute(
                """
                UPDATE actions SET status = 'rejected',
                    result = 'Human reviewer rejected the simulated action; no external action was taken.',
                    updated_at = ?
                WHERE run_id = ?
                """,
                (decided_at, run_id),
            )
            connection.execute(
                """
                UPDATE runs SET status = 'completed', action_status = 'rejected',
                    approval_status = 'rejected'
                WHERE run_id = ?
                """,
                (run_id,),
            )
            _insert_audit(
                connection,
                run_id,
                "approval_rejected",
                "Human reviewer rejected the prepared simulated action.",
                {"reviewer": normalized_reviewer, "note": note.strip()},
            )

    result = get_run_details(run_id, db_path)
    if result is None:
        raise RuntimeError(f"Run {run_id} was updated but could not be reloaded.")
    return result
