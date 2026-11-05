"""Deterministic, auditable ORBIT intelligence extensions.

All shipment inputs remain explicitly simulated. Scores are rule-based support
indicators, not calibrated probabilities or model confidence.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from storage import connect, get_run_details, initialize_database, utc_now


def adaptive_plan(shipment: Mapping[str, Any], complaint: str, policy: Mapping[str, Any]) -> dict[str, Any]:
    """Select only the specialist stages warranted by case characteristics."""
    claim_type = shipment.get("claim_type", "unknown")
    missing = [k for k, required in policy.items() if k == "required_documents"
               for doc in required if not shipment.get("documents", {}).get(doc, False)]
    high_exposure = float(shipment.get("claim_amount", 0) or 0) >= 50000
    investigation = bool(missing or claim_type == "not_received" or high_exposure
                         or any(word in complaint.lower() for word in ("conflict", "contradict", "dispute")))
    selected = [
        ("Research Agent", "Retrieve shipment, tracking, documents and applicable local policy."),
        ("Analysis Agent", "Apply the claim-type policy checks to retrieved evidence."),
    ]
    if investigation:
        selected.append(("Investigation Agent", "Resolve missing evidence, disputes or elevated exposure."))
    selected.append(("Validation Agent", "Challenge unsupported conclusions and verify policy consistency."))
    if investigation:
        selected.append(("Debate Engine", "Compare independent positions and preserve unresolved challenges."))
    selected.append(("Uncertainty Engine", "Calculate transparent evidence support and escalation route."))
    selected.append(("Memory Agent", "Retrieve structured historical examples and reviewer feedback."))
    skipped = []
    if not investigation:
        skipped.append({"agent": "Investigation Agent", "reason": "No missing required evidence, dispute, or high-exposure signal detected."})
        skipped.append({"agent": "Debate Engine", "reason": "No investigation trigger; debate is not required for this case."})
    return {
        "complexity": "high" if high_exposure or (missing and claim_type == "not_received") else "moderate" if investigation else "low",
        "selected": [{"agent": a, "reason": r, "status": "planned"} for a, r in selected],
        "skipped": skipped,
        "max_debate_rounds": 2,
    }


def build_debate(research: Mapping[str, Any], analysis: Mapping[str, Any], validation: Mapping[str, Any]) -> dict[str, Any]:
    """Create a bounded, evidence-linked challenge record from actual agent outputs."""
    evidence = research.get("evidence", [])
    evidence_ids = [f"E{i+1}" for i in range(len(evidence))]
    missing = research.get("missing_documents", [])
    decision = analysis.get("decision", "pending")
    arguments = [{
        "round": 1, "agent": "Analysis Agent", "position": decision,
        "supporting_evidence_ids": evidence_ids[:3],
        "policy_references": [research.get("policy", {}).get("title", "Local demo policy")],
        "support_level": "rule-derived", "counterargument": None,
        "timestamp": utc_now(), "revision_reason": "Initial policy evaluation."
    }]
    conflict = bool(missing) or not validation.get("valid", False) or decision == "investigation_required"
    if conflict:
        arguments.append({
            "round": 1, "agent": "Validation Agent", "position": "challenge",
            "supporting_evidence_ids": evidence_ids[-2:],
            "policy_references": [research.get("policy", {}).get("title", "Local demo policy")],
            "support_level": "rule-derived",
            "counterargument": "The recommendation cannot be treated as conclusive while required evidence is missing or delivery remains disputed.",
            "timestamp": utc_now(), "revision_reason": "Independent validation challenge."
        })
        arguments.append({
            "round": 2, "agent": "Investigation Agent", "position": "request_more_evidence",
            "supporting_evidence_ids": [],
            "policy_references": [research.get("policy", {}).get("title", "Local demo policy")],
            "support_level": "insufficient_evidence",
            "counterargument": "No source record currently resolves the outstanding evidence gap.",
            "timestamp": utc_now(), "revision_reason": "No new evidence supplied; preserve the hold."
        })
    return {
        "max_rounds": 2, "rounds_used": 2 if conflict else 1,
        "status": "unresolved" if conflict else "resolved",
        "arguments": arguments,
        "unresolved_questions": [f"Provide {item.replace('_', ' ')}." for item in missing]
            + (["Can delivery be verified with recipient-level proof?"] if decision == "investigation_required" else []),
        "termination_reason": "Maximum configured rounds reached; unresolved issues remain." if conflict else "No material disagreement detected."
    }


def uncertainty_assessment(research: Mapping[str, Any], analysis: Mapping[str, Any],
                           validation: Mapping[str, Any], debate: Mapping[str, Any]) -> dict[str, Any]:
    """Transparent weighted support heuristic; deliberately not a probability."""
    required = research.get("policy", {}).get("required_documents", [])
    docs = research.get("shipment", {}).get("documents", {})
    completeness = (sum(bool(docs.get(doc)) for doc in required) / len(required) * 100) if required else 100.0
    evidence = research.get("evidence", [])
    reliability = 85.0 if evidence else 0.0  # local sample records are internally supplied, not carrier-verified
    consistency = 100.0 if validation.get("valid") else 30.0
    policy_clarity = 85.0 if research.get("policy", {}).get("summary") else 30.0
    disagreement_penalty = 25.0 if debate.get("status") == "unresolved" else 0.0
    score = round(max(0, min(100, .35*completeness + .20*reliability + .20*consistency + .15*policy_clarity + .10*100 - disagreement_penalty)), 1)
    if debate.get("status") == "unresolved":
        route = "UNRESOLVED CONFLICT"
    elif score >= 80:
        route = "HIGH SUPPORT"
    elif score >= 55:
        route = "MODERATE SUPPORT"
    else:
        route = "LOW SUPPORT"
    return {
        "evidence_completeness": round(completeness, 1),
        "decision_support_score": score,
        "model_confidence": None,
        "predictive_calibration": "Not measured; requires labeled evaluation data.",
        "route": route,
        "weights": {"completeness": .35, "reliability": .20, "consistency": .20, "policy_clarity": .15, "historical_similarity": .10},
        "components": {"evidence_reliability": reliability, "evidence_consistency": consistency,
                       "policy_clarity": policy_clarity, "historical_similarity": 0},
        "reasons": [
            f"{len(evidence)} evidence items were retrieved from the local simulated case.",
            f"{len(research.get('missing_documents', []))} required document(s) are missing.",
            "Agent disagreement remains unresolved." if debate.get("status") == "unresolved" else "No unresolved debate recorded.",
            "Local policy examples and sample records are not independently carrier-verified."
        ]
    }


def decision_graph(state: Mapping[str, Any]) -> dict[str, Any]:
    nodes = [
        ("claim", "Customer complaint", "input"),
        ("shipment", "Shipment information", "research"),
        ("evidence", "Retrieved evidence", "research"),
        ("policy", "Policy evaluation", "analysis"),
        ("findings", "Independent agent findings", "analysis"),
        ("debate", "Agent disagreement", "debate"),
        ("uncertainty", "Uncertainty assessment", "uncertainty"),
        ("validation", "Final validation", "validation"),
        ("recommendation", "Recommendation", "analysis"),
    ]
    output = []
    for node_id, label, key in nodes:
        output.append({"id": node_id, "label": label, "available": key == "input" or key in state,
                       "details": state.get(key, {}) if key != "input" else {"source": "Submitted claim"}})
    edges = [{"from": nodes[i][0], "to": nodes[i+1][0], "relationship": "informs"} for i in range(len(nodes)-1)]
    return {"nodes": output, "edges": edges}


def init_memory(db_path: str | Path | None = None) -> None:
    initialize_database(db_path)
    with connect(db_path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS orbit_feedback (
            feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL, shipment_id TEXT NOT NULL,
            original_recommendation TEXT, human_decision TEXT NOT NULL,
            correction_reason TEXT, reviewer TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orbit_feedback_shipment ON orbit_feedback(shipment_id)")


def save_feedback(run: Mapping[str, Any], decision: str, reviewer: str,
                  reason: str = "", db_path: str | Path | None = None,
                  owner_email: str | None = None, is_admin: bool = False) -> None:
    if decision not in {"approved", "rejected", "investigate"}:
        raise ValueError("Decision must be approved, rejected, or investigate.")
    if not reviewer.strip():
        raise ValueError("Reviewer name is required.")
    if owner_email is not None and get_run_details(
        run["run_id"], db_path, owner_email=owner_email, is_admin=is_admin
    ) is None:
        raise PermissionError("This claim is unavailable to this account.")
    init_memory(db_path)
    with connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        version = conn.execute("SELECT COALESCE(MAX(version),0)+1 FROM orbit_feedback WHERE run_id=?",
                               (run["run_id"],)).fetchone()[0]
        conn.execute("""INSERT INTO orbit_feedback
            (run_id,shipment_id,original_recommendation,human_decision,correction_reason,reviewer,version,created_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (run["run_id"], run["shipment_id"], run.get("recommendation"), decision,
             reason.strip(), reviewer.strip(), version, utc_now()))


def list_feedback(
    db_path: str | Path | None = None,
    owner_email: str | None = None,
    is_admin: bool = False,
) -> list[dict[str, Any]]:
    init_memory(db_path)
    with connect(db_path) as conn:
        query = """
            SELECT feedback.*
            FROM orbit_feedback AS feedback
            JOIN runs ON runs.run_id = feedback.run_id
        """
        parameters: tuple[str, ...] = ()
        if owner_email is not None and not is_admin:
            query += " WHERE runs.owner_email = ?"
            parameters = (owner_email.strip().lower(),)
        query += " ORDER BY feedback.feedback_id DESC"
        return [
            dict(row)
            for row in conn.execute(query, parameters).fetchall()
        ]


def delete_feedback(
    feedback_id: int,
    db_path: str | Path | None = None,
    owner_email: str | None = None,
    is_admin: bool = False,
) -> None:
    init_memory(db_path)
    with connect(db_path) as conn:
        query = "DELETE FROM orbit_feedback WHERE feedback_id = ?"
        parameters: tuple[Any, ...] = (feedback_id,)
        if owner_email is not None and not is_admin:
            query += """
                AND run_id IN (SELECT run_id FROM runs WHERE owner_email = ?)
            """
            parameters = (feedback_id, owner_email.strip().lower())
        result = conn.execute(query, parameters)
        if result.rowcount != 1:
            raise PermissionError("This feedback entry is unavailable to this account.")


def similar_feedback(
    shipment_id: str,
    db_path: str | Path | None = None,
    owner_email: str | None = None,
    is_admin: bool = False,
) -> list[dict[str, Any]]:
    return [
        row
        for row in list_feedback(db_path, owner_email, is_admin)
        if row["shipment_id"] == shipment_id
    ][:5]


def simulated_scenarios() -> list[dict[str, str]]:
    return [
        {"name":"Normal shipment delay","difficulty":"easy","expected":"Check delay threshold and claim window"},
        {"name":"Lost shipment","difficulty":"moderate","expected":"Check last-scan threshold and required records"},
        {"name":"Damaged shipment","difficulty":"moderate","expected":"Verify photos and reporting window"},
        {"name":"Delivered but disputed","difficulty":"hard","expected":"Escalate pending proof of delivery"},
        {"name":"Duplicate documents","difficulty":"hard","expected":"Flag duplicate evidence before counting completeness"},
        {"name":"Conflicting tracking records","difficulty":"hard","expected":"Preserve conflict and request human review"},
        {"name":"Outdated policy document","difficulty":"hard","expected":"Flag policy freshness for human review"},
        {"name":"Missing timestamps","difficulty":"moderate","expected":"Treat chronology as incomplete"},
        {"name":"Incorrect shipment identifier","difficulty":"easy","expected":"Reject lookup without creating a workflow"},
        {"name":"Ambiguous policy interpretation","difficulty":"hard","expected":"Escalate policy ambiguity"},
    ]
