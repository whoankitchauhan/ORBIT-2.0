import tempfile
import unittest
from pathlib import Path

from evaluation import run_evaluation
from auth import initialize_auth_database, promote_user_to_admin, register_user
from pipeline import (
    WorkflowError,
    decide_approval,
    execute_simulated_action,
    resume_claim_workflow,
    start_claim_workflow,
)
from sample_data import EXPECTED_DECISIONS, SHIPMENTS
from storage import get_run_details, initialize_database, list_runs
from orbit_intelligence import (
    adaptive_plan, build_debate, uncertainty_assessment, decision_graph,
    save_feedback, list_feedback, delete_feedback,
)


class OrbitWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="orbit-tests-")
        self.db_path = Path(self.temp_dir.name) / "orbit.sqlite3"
        self.auth_db_path = Path(self.temp_dir.name) / "users.sqlite3"
        initialize_database(self.db_path)
        initialize_auth_database(self.auth_db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def complaint_for(self, shipment_id: str) -> str:
        return next(case["complaint"] for case in SHIPMENTS if case["shipment_id"] == shipment_id)

    def create_admin(self) -> str:
        email = "admin@example.com"
        register_user(email, "secure-admin-password", self.auth_db_path)
        promote_user_to_admin(email, self.auth_db_path)
        return email

    def test_all_sample_cases_match_expected_decisions(self) -> None:
        for shipment_id, expected in EXPECTED_DECISIONS.items():
            with self.subTest(shipment_id=shipment_id):
                run = start_claim_workflow(
                    shipment_id,
                    self.complaint_for(shipment_id),
                    self.db_path,
                )
                self.assertEqual(run["decision"], expected)
                self.assertEqual(run["status"], "awaiting_approval" if expected in {"eligible", "ineligible"} else "completed")
                self.assertEqual(
                    [event["status"] for event in run["events"]],
                    ["completed", "completed", "completed", "completed"],
                )

    def test_evidence_and_missing_documents_are_persisted(self) -> None:
        run = start_claim_workflow(
            "DLV-2403",
            self.complaint_for("DLV-2403"),
            self.db_path,
        )
        self.assertIn("tracking_event", {item["kind"] for item in run["state"]["research"]["evidence"]})
        self.assertEqual(run["state"]["research"]["missing_documents"], ["proof_of_delivery"])
        self.assertEqual(run["state"]["analysis"]["decision"], "needs_documents")
        self.assertTrue(run["state"]["validation"]["valid"])

    def test_sensitive_action_is_blocked_until_human_approval(self) -> None:
        admin_email = self.create_admin()
        run = start_claim_workflow(
            "DLV-2401",
            self.complaint_for("DLV-2401"),
            self.db_path,
        )
        self.assertEqual(run["action"]["status"], "awaiting_approval")
        with self.assertRaises(PermissionError):
            execute_simulated_action(run["run_id"], self.db_path)
        unchanged = get_run_details(run["run_id"], self.db_path)
        self.assertEqual(unchanged["approval"]["status"], "pending")
        self.assertEqual(unchanged["action"]["status"], "awaiting_approval")

        approved = decide_approval(
            run["run_id"],
            "approved",
            admin_email,
            "Verified supporting records.",
            self.db_path,
            self.auth_db_path,
        )
        self.assertEqual(approved["status"], "completed")
        self.assertEqual(approved["approval"]["status"], "approved")
        self.assertEqual(approved["action"]["status"], "simulated_executed")
        self.assertIn("No Delhivery system", approved["action"]["result"])
        self.assertIn("simulated_action_executed", [entry["event_type"] for entry in approved["audit"]])

    def test_rejected_sensitive_action_is_not_executed(self) -> None:
        admin_email = self.create_admin()
        run = start_claim_workflow(
            "DLV-2404",
            self.complaint_for("DLV-2404"),
            self.db_path,
        )
        rejected = decide_approval(
            run["run_id"],
            "rejected",
            admin_email,
            db_path=self.db_path,
            auth_db_path=self.auth_db_path,
        )
        self.assertEqual(rejected["approval"]["status"], "rejected")
        self.assertEqual(rejected["action"]["status"], "rejected")
        self.assertNotIn("simulated_action_executed", [entry["event_type"] for entry in rejected["audit"]])

    def test_failed_run_resumes_from_persisted_agent_result(self) -> None:
        injected = False

        def fail_once(stage: str) -> None:
            nonlocal injected
            if stage == "analysis" and not injected:
                injected = True
                raise RuntimeError("test-only failure")

        with self.assertRaises(WorkflowError) as context:
            start_claim_workflow(
                "DLV-2401",
                self.complaint_for("DLV-2401"),
                self.db_path,
                fault_injector=fail_once,
            )
        run_id = context.exception.run_id
        failed = get_run_details(run_id, self.db_path)
        self.assertEqual(failed["status"], "failed")
        self.assertIn("research", failed["state"])
        self.assertEqual(failed["state"].get("analysis"), None)
        self.assertTrue(any(event["status"] == "failed" for event in failed["events"]))

        resumed = resume_claim_workflow(run_id, self.db_path)
        self.assertEqual(resumed["status"], "awaiting_approval")
        self.assertEqual(resumed["decision"], "eligible")
        self.assertEqual(
            sum(event["agent"] == "Research Agent" and event["status"] == "completed" for event in resumed["events"]),
            1,
        )
        self.assertIn("workflow_resumed", [entry["event_type"] for entry in resumed["audit"]])

    def test_input_validation_happens_before_a_run_is_created(self) -> None:
        with self.assertRaisesRegex(ValueError, "DLV-0000"):
            start_claim_workflow("bad-id", "A valid complaint with enough characters.", self.db_path)
        with self.assertRaisesRegex(ValueError, "10 and 1,000"):
            start_claim_workflow("DLV-2401", "short", self.db_path)
        with self.assertRaisesRegex(ValueError, "No simulated shipment"):
            start_claim_workflow("DLV-9999", "A valid complaint with enough characters.", self.db_path)
        self.assertEqual(list_runs(self.db_path), [])

    def test_intelligence_state_is_persisted_and_explainable(self) -> None:
        run = start_claim_workflow(
            "DLV-2403", self.complaint_for("DLV-2403"), self.db_path
        )
        state = run["state"]
        self.assertIn("Investigation Agent", [x["agent"] for x in state["adaptive_plan"]["selected"]])
        self.assertEqual(state["debate"]["status"], "unresolved")
        self.assertEqual(state["uncertainty"]["route"], "UNRESOLVED CONFLICT")
        self.assertTrue(state["decision_graph"]["nodes"])
        self.assertTrue(any(node["id"] == "recommendation" for node in state["decision_graph"]["nodes"]))

    def test_feedback_is_versioned_separate_and_deletable(self) -> None:
        run = start_claim_workflow(
            "DLV-2401", self.complaint_for("DLV-2401"), self.db_path
        )
        save_feedback(run, "rejected", "Reviewer", "Needs a second review.", self.db_path)
        rows = list_feedback(self.db_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["version"], 1)
        self.assertEqual(rows[0]["human_decision"], "rejected")
        delete_feedback(rows[0]["feedback_id"], self.db_path)
        self.assertEqual(list_feedback(self.db_path), [])

    def test_claim_history_and_feedback_are_scoped_to_the_owner(self) -> None:
        first_run = start_claim_workflow(
            "DLV-2401",
            self.complaint_for("DLV-2401"),
            self.db_path,
            owner_email="first@example.com",
        )
        second_run = start_claim_workflow(
            "DLV-2402",
            self.complaint_for("DLV-2402"),
            self.db_path,
            owner_email="second@example.com",
        )
        self.assertEqual(
            [run["run_id"] for run in list_runs(
                self.db_path, owner_email="first@example.com"
            )],
            [first_run["run_id"]],
        )
        self.assertEqual(len(list_runs(self.db_path, is_admin=True)), 2)
        self.assertIsNone(
            get_run_details(
                first_run["run_id"], self.db_path, owner_email="second@example.com"
            )
        )
        with self.assertRaises(ValueError):
            resume_claim_workflow(
                first_run["run_id"], self.db_path, owner_email="second@example.com"
            )

        save_feedback(
            first_run,
            "rejected",
            "first@example.com",
            "Needs a second look.",
            self.db_path,
            owner_email="first@example.com",
        )
        self.assertEqual(
            len(list_feedback(self.db_path, owner_email="first@example.com")), 1
        )
        self.assertEqual(
            list_feedback(self.db_path, owner_email="second@example.com"), []
        )
        feedback_id = list_feedback(self.db_path)[0]["feedback_id"]
        with self.assertRaises(PermissionError):
            delete_feedback(
                feedback_id, self.db_path, owner_email="second@example.com"
            )
        delete_feedback(
            feedback_id, self.db_path, owner_email="first@example.com"
        )
        self.assertEqual(list_feedback(self.db_path), [])
        self.assertEqual(second_run["owner_email"], "second@example.com")

    def test_only_a_persisted_admin_can_approve_a_sensitive_action(self) -> None:
        register_user("reviewer@example.com", "secure-user-password", self.auth_db_path)
        run = start_claim_workflow(
            "DLV-2401",
            self.complaint_for("DLV-2401"),
            self.db_path,
            owner_email="customer@example.com",
        )
        with self.assertRaises(PermissionError):
            decide_approval(
                run["run_id"],
                "approved",
                "reviewer@example.com",
                db_path=self.db_path,
                auth_db_path=self.auth_db_path,
            )
        unchanged = get_run_details(run["run_id"], self.db_path)
        self.assertEqual(unchanged["approval"]["status"], "pending")
        self.assertEqual(unchanged["action"]["status"], "awaiting_approval")

        promote_user_to_admin("reviewer@example.com", self.auth_db_path)
        approved = decide_approval(
            run["run_id"],
            "approved",
            "reviewer@example.com",
            db_path=self.db_path,
            auth_db_path=self.auth_db_path,
        )
        self.assertEqual(approved["approval"]["reviewer"], "reviewer@example.com")
        self.assertEqual(approved["action"]["status"], "simulated_executed")

    def test_evaluation_reports_baseline_and_safety_results(self) -> None:
        report = run_evaluation()
        self.assertEqual(report["case_count"], len(SHIPMENTS))
        self.assertEqual(report["orbit_accuracy"], 100)
        self.assertEqual(
            report["baseline_accuracy"],
            100 * sum(decision == "eligible" for decision in EXPECTED_DECISIONS.values())
            / len(EXPECTED_DECISIONS),
        )
        self.assertEqual(report["orbit_evidence_completeness"], 100)
        self.assertEqual(report["orbit_recovery"], "1/1")
        self.assertEqual(report["orbit_unauthorized_block"], "1/1")
        self.assertEqual(report["baseline_unauthorized_block"], "0/1")
        self.assertGreaterEqual(report["orbit_mean_processing_ms"], 0)
        self.assertGreaterEqual(report["baseline_mean_processing_ms"], 0)


if __name__ == "__main__":
    unittest.main()
