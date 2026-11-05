"""Small reproducible comparison against an intentionally simple baseline."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from agents import analysis_agent, research_agent, validation_agent, action_agent
from pipeline import (
    WorkflowError,
    execute_simulated_action,
    resume_claim_workflow,
    start_claim_workflow,
)
from sample_data import EXPECTED_DECISIONS, POLICIES, SHIPMENTS
from storage import get_run_details


def run_evaluation() -> dict[str, Any]:
    """Measure decisions, evidence coverage, processing, recovery, and action gating."""
    orbit_correct = 0
    baseline_correct = 0
    total_expected_evidence = 0
    total_retrieved_evidence = 0
    orbit_elapsed_ms = 0.0
    baseline_elapsed_ms = 0.0
    case_results = []

    policies_by_type = {policy["claim_type"]: policy for policy in POLICIES}
    for shipment in SHIPMENTS:
        expected = EXPECTED_DECISIONS[shipment["shipment_id"]]
        started = time.perf_counter()
        research = research_agent(
            shipment,
            shipment["complaint"],
            policies_by_type[shipment["claim_type"]],
        )
        analysis = analysis_agent(research)
        validation = validation_agent(research, analysis)
        action = action_agent(analysis, validation)
        orbit_elapsed_ms += (time.perf_counter() - started) * 1000

        baseline_started = time.perf_counter()
        baseline_decision = "eligible" if shipment["complaint"].strip() else "ineligible"
        baseline_elapsed_ms += (time.perf_counter() - baseline_started) * 1000

        expected_evidence = (
            1
            + len(shipment["tracking_events"])
            + sum(bool(present) for present in shipment["documents"].values())
            + 1
        )
        total_expected_evidence += expected_evidence
        total_retrieved_evidence += len(research["evidence"])
        orbit_correct += analysis["decision"] == expected
        baseline_correct += baseline_decision == expected
        case_results.append({
            "shipment_id": shipment["shipment_id"],
            "expected": expected,
            "orbit_decision": analysis["decision"],
            "baseline_decision": baseline_decision,
            "evidence_found": len(research["evidence"]),
            "evidence_expected": expected_evidence,
            "recommendation_validated": validation["valid"],
            "prepared_action": action["action_type"],
        })

    case_count = len(SHIPMENTS)
    evidence_coverage = (
        100 * total_retrieved_evidence / total_expected_evidence
        if total_expected_evidence else 0
    )

    recovery_passed = False
    unauthorized_blocked = False
    with tempfile.TemporaryDirectory(prefix="orbit-evaluation-") as directory:
        db_path = Path(directory) / "evaluation.sqlite3"
        failed_once = False

        def fail_once_at_analysis(stage: str) -> None:
            nonlocal failed_once
            if stage == "analysis" and not failed_once:
                failed_once = True
                raise RuntimeError("evaluation-only injected failure")

        try:
            start_claim_workflow(
                "DLV-2401",
                SHIPMENTS[0]["complaint"],
                db_path=db_path,
                fault_injector=fail_once_at_analysis,
            )
        except WorkflowError as error:
            failed_run = get_run_details(error.run_id, db_path)
            if failed_run and failed_run["status"] == "failed" and "research" in failed_run["state"]:
                recovered = resume_claim_workflow(error.run_id, db_path)
                recovery_passed = recovered["status"] == "awaiting_approval"

        pending_run = start_claim_workflow(
            "DLV-2402",
            SHIPMENTS[1]["complaint"],
            db_path=db_path,
        )
        try:
            execute_simulated_action(pending_run["run_id"], db_path)
        except PermissionError:
            unchanged = get_run_details(pending_run["run_id"], db_path)
            unauthorized_blocked = bool(
                unchanged
                and unchanged["approval"]["status"] == "pending"
                and unchanged["action"]["status"] == "awaiting_approval"
            )

    return {
        "case_count": case_count,
        "orbit_accuracy": 100 * orbit_correct / case_count if case_count else 0,
        "baseline_accuracy": 100 * baseline_correct / case_count if case_count else 0,
        "orbit_evidence_completeness": evidence_coverage,
        "baseline_evidence_completeness": 0.0,
        "orbit_mean_processing_ms": orbit_elapsed_ms / case_count if case_count else 0,
        "baseline_mean_processing_ms": baseline_elapsed_ms / case_count if case_count else 0,
        "orbit_recovery": "1/1" if recovery_passed else "0/1",
        "baseline_recovery": "0/1",
        "orbit_unauthorized_block": "1/1" if unauthorized_blocked else "0/1",
        "baseline_unauthorized_block": "0/1",
        "cases": case_results,
        "baseline_description": (
            "Always marks a complaint eligible, retrieves no evidence, has no retry, "
            "and has no approval gate."
        ),
    }
