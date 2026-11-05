"""Small, deterministic claim-resolution agents used by the supervisor."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def research_agent(
    shipment: Mapping[str, Any],
    complaint: str,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Collect the simulated shipment, tracking, document, and policy evidence."""
    evidence = [
        {
            "kind": "shipment_record",
            "label": "Simulated Delhivery shipment record",
            "detail": (
                f"{shipment['shipment_id']}: {shipment['status']}; "
                f"{shipment['origin']} to {shipment['destination']}"
            ),
        }
    ]
    for event in shipment["tracking_events"]:
        evidence.append({"kind": "tracking_event", "label": "Tracking history", "detail": event})
    documents = shipment["documents"]
    for document, present in documents.items():
        if present:
            evidence.append({
                "kind": "document",
                "label": document.replace("_", " ").title(),
                "detail": f"{document.replace('_', ' ').title()} is available in the simulated case file.",
            })
    evidence.append({
        "kind": "claim_policy",
        "label": f"Local demo policy: {policy['title']}",
        "detail": policy["summary"],
    })
    missing_documents = [
        document
        for document in policy["required_documents"]
        if not documents.get(document, False)
    ]
    return {
        "shipment": dict(shipment),
        "complaint": complaint,
        "policy": dict(policy),
        "evidence": evidence,
        "missing_documents": missing_documents,
    }


def analysis_agent(research: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the visible local demo policy to evidence gathered by Research."""
    shipment = research["shipment"]
    policy = research["policy"]
    missing_documents = research["missing_documents"]
    claim_type = shipment["claim_type"]
    policy_checks: list[dict[str, str]] = []

    if claim_type == "delay":
        delay_passes = shipment["delay_days"] >= policy["minimum_delay_days"]
        policy_checks.append({
            "rule": "Minimum transit delay",
            "result": "pass" if delay_passes else "fail",
            "detail": (
                f"{shipment['delay_days']} days recorded; "
                f"{policy['minimum_delay_days']} days required."
            ),
        })
        age_passes = shipment["claim_age_days"] <= policy["maximum_claim_age_days"]
        policy_checks.append({
            "rule": "Claim filing window",
            "result": "pass" if age_passes else "fail",
            "detail": (
                f"Claim opened {shipment['claim_age_days']} days after the event; "
                f"limit is {policy['maximum_claim_age_days']} days."
            ),
        })
    elif claim_type == "damage":
        report_passes = shipment["damage_reported_days_ago"] <= policy["maximum_report_days"]
        policy_checks.append({
            "rule": "Damage reporting window",
            "result": "pass" if report_passes else "fail",
            "detail": (
                f"Reported {shipment['damage_reported_days_ago']} days after delivery; "
                f"limit is {policy['maximum_report_days']} days."
            ),
        })
    elif claim_type == "lost":
        scan_passes = shipment["days_since_last_scan"] >= policy["minimum_no_scan_days"]
        policy_checks.append({
            "rule": "Lost-shipment scan threshold",
            "result": "pass" if scan_passes else "fail",
            "detail": (
                f"No scan for {shipment['days_since_last_scan']} days; "
                f"{policy['minimum_no_scan_days']} days required."
            ),
        })
    elif claim_type == "not_received":
        policy_checks.append({
            "rule": "Proof of delivery for dispute review",
            "result": "pending" if "proof_of_delivery" in missing_documents else "pass",
            "detail": "A delivery dispute is not resolved automatically; proof is required for human review.",
        })

    policy_checks.append({
        "rule": "Required documents",
        "result": "pending" if missing_documents else "pass",
        "detail": (
            "Missing: " + ", ".join(missing_documents)
            if missing_documents else "All policy-required documents are present."
        ),
    })

    failed_checks = [check for check in policy_checks if check["result"] == "fail"]
    if failed_checks:
        decision = "ineligible"
        recommendation = "The claim does not meet the recorded demo policy threshold."
    elif missing_documents:
        decision = "needs_documents"
        recommendation = "Request the missing documents before making an eligibility decision."
    elif claim_type == "not_received":
        decision = "investigation_required"
        recommendation = "Route the delivery dispute for human investigation; do not decide it automatically."
    else:
        decision = "eligible"
        recommendation = "The available evidence meets the recorded demo policy checks."

    return {
        "decision": decision,
        "recommendation": recommendation,
        "policy_checks": policy_checks,
        "failed_checks": failed_checks,
        "missing_documents": list(missing_documents),
    }


def validation_agent(
    research: Mapping[str, Any],
    analysis: Mapping[str, Any],
) -> dict[str, Any]:
    """Check that the proposed decision agrees with its evidence and policy checks."""
    decision = analysis["decision"]
    missing_documents = research["missing_documents"]
    failed_checks = analysis["failed_checks"]
    checks = [
        {
            "rule": "No missing required documents for an eligible decision",
            "passed": not (decision == "eligible" and bool(missing_documents)),
        },
        {
            "rule": "No failed policy checks for an eligible decision",
            "passed": not (decision == "eligible" and bool(failed_checks)),
        },
        {
            "rule": "Document requests identify missing evidence",
            "passed": not (decision == "needs_documents" and not missing_documents),
        },
    ]
    valid = all(check["passed"] for check in checks)
    return {
        "valid": valid,
        "checks": checks,
        "message": (
            "Recommendation is consistent with the evidence."
            if valid else "Recommendation failed validation and is held for human review."
        ),
    }


def action_agent(
    analysis: Mapping[str, Any],
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    """Prepare a next step; never calls a carrier, payment, or support system."""
    if not validation["valid"]:
        return {
            "action_type": "hold_for_review",
            "requires_approval": False,
            "status": "prepared",
            "description": "Hold the case for manual review; no external action was taken.",
        }

    decision = analysis["decision"]
    if decision == "eligible":
        return {
            "action_type": "issue_refund",
            "requires_approval": True,
            "status": "awaiting_approval",
            "description": "Prepare a simulated refund action; a human must approve before execution.",
        }
    if decision == "ineligible":
        return {
            "action_type": "close_claim",
            "requires_approval": True,
            "status": "awaiting_approval",
            "description": "Prepare a simulated claim closure; a human must approve before execution.",
        }
    if decision == "needs_documents":
        return {
            "action_type": "request_documents",
            "requires_approval": False,
            "status": "prepared",
            "description": "Prepare a document request for review; nothing has been sent.",
        }
    return {
        "action_type": "manual_investigation",
        "requires_approval": False,
        "status": "prepared",
        "description": "Prepare a manual investigation; no external ticket was created.",
    }
