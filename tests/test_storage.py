import sqlite3
import tempfile
import unittest
from pathlib import Path

from storage import initialize_database, list_runs


class StorageMigrationTests(unittest.TestCase):
    def test_existing_workflow_runs_gain_owner_column_without_data_loss(self) -> None:
        with tempfile.TemporaryDirectory(prefix="orbit-storage-tests-") as directory:
            db_path = Path(directory) / "legacy.sqlite3"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    """
                    CREATE TABLE runs (
                        run_id TEXT PRIMARY KEY,
                        shipment_id TEXT NOT NULL,
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
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO runs (run_id, shipment_id, complaint, status, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("legacy-run", "DLV-2401", "A legacy complaint", "completed", "2026-01-01"),
                )
                connection.commit()
            finally:
                connection.close()

            initialize_database(db_path)
            user_runs = list_runs(db_path, owner_email="student@example.com")
            admin_runs = list_runs(db_path, is_admin=True)
            connection = sqlite3.connect(db_path)
            try:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(runs)")
                }
                legacy_run = connection.execute(
                    "SELECT run_id, complaint, owner_email FROM runs WHERE run_id = ?",
                    ("legacy-run",),
                ).fetchone()
            finally:
                connection.close()

        self.assertIn("owner_email", columns)
        self.assertEqual(legacy_run, ("legacy-run", "A legacy complaint", None))
        self.assertEqual(user_runs, [])
        self.assertEqual([run["run_id"] for run in admin_runs], ["legacy-run"])


if __name__ == "__main__":
    unittest.main()
