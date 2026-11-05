import sqlite3
import tempfile
import unittest
from pathlib import Path

from auth import (
    authenticate_user,
    get_user,
    get_theme_preference,
    initialize_auth_database,
    list_users,
    promote_user_to_admin,
    promote_user_to_admin_by_admin,
    register_user,
    set_theme_preference,
)


class AuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="orbit-auth-tests-")
        self.db_path = Path(self.temp_dir.name) / "users.sqlite3"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_registration_hashes_password_and_assigns_user_role(self) -> None:
        created, message = register_user(
            " Student@Example.com ", "a-long-demo-password", self.db_path
        )
        self.assertTrue(created, message)
        account = authenticate_user(
            "student@example.com", "a-long-demo-password", self.db_path
        )
        self.assertEqual(account["role"], "user")
        self.assertIsNone(
            authenticate_user(
                "student@example.com", "incorrect-password", self.db_path
            )
        )
        duplicate, _ = register_user(
            "student@example.com", "another-demo-password", self.db_path
        )
        self.assertFalse(duplicate)

        connection = sqlite3.connect(self.db_path)
        try:
            salt, password_hash = connection.execute(
                "SELECT salt, password_hash FROM users WHERE email = ?",
                ("student@example.com",),
            ).fetchone()
        finally:
            connection.close()
        self.assertNotEqual(password_hash, b"a-long-demo-password")
        self.assertEqual(len(salt), 16)

    def test_local_admin_promotion_changes_persisted_role(self) -> None:
        register_user("admin@example.com", "a-long-demo-password", self.db_path)
        promote_user_to_admin("admin@example.com", self.db_path)
        self.assertEqual(
            get_user("admin@example.com", self.db_path)["role"], "admin"
        )
        with self.assertRaisesRegex(ValueError, "No account exists"):
            promote_user_to_admin("missing@example.com", self.db_path)

    def test_user_directory_and_role_changes_require_admin(self) -> None:
        register_user("admin@example.com", "a-long-demo-password", self.db_path)
        register_user("user@example.com", "a-long-demo-password", self.db_path)
        with self.assertRaises(PermissionError):
            list_users("user@example.com", self.db_path)
        with self.assertRaises(PermissionError):
            promote_user_to_admin_by_admin(
                "user@example.com", "user@example.com", self.db_path
            )
        self.assertEqual(get_user("user@example.com", self.db_path)["role"], "user")

        promote_user_to_admin("admin@example.com", self.db_path)
        accounts = list_users("admin@example.com", self.db_path)
        self.assertEqual(
            [(account["email"], account["role"]) for account in accounts],
            [("admin@example.com", "admin"), ("user@example.com", "user")],
        )
        promote_user_to_admin_by_admin(
            "admin@example.com", "user@example.com", self.db_path
        )
        self.assertEqual(get_user("user@example.com", self.db_path)["role"], "admin")

    def test_existing_accounts_migrate_to_normal_user_role(self) -> None:
        connection = sqlite3.connect(self.db_path)
        try:
            connection.execute(
                """
                CREATE TABLE users (
                    email TEXT PRIMARY KEY,
                    salt BLOB NOT NULL,
                    password_hash BLOB NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "INSERT INTO users (email, salt, password_hash) VALUES (?, ?, ?)",
                ("existing@example.com", b"legacy-salt", b"legacy-hash"),
            )
            connection.commit()
        finally:
            connection.close()

        initialize_auth_database(self.db_path)
        account = get_user("existing@example.com", self.db_path)
        self.assertEqual(account["role"], "user")

    def test_theme_preference_is_persisted_per_account(self) -> None:
        register_user("theme@example.com", "a-long-demo-password", self.db_path)
        self.assertIsNone(get_theme_preference("theme@example.com", self.db_path))

        set_theme_preference("THEME@example.com", "dark", self.db_path)
        self.assertEqual(
            get_theme_preference("theme@example.com", self.db_path), "Dark"
        )
        set_theme_preference("theme@example.com", "System", self.db_path)
        self.assertEqual(
            get_theme_preference("theme@example.com", self.db_path), "System"
        )

    def test_theme_preference_rejects_unknown_mode_or_account(self) -> None:
        register_user("theme@example.com", "a-long-demo-password", self.db_path)
        with self.assertRaisesRegex(ValueError, "Theme must be"):
            set_theme_preference("theme@example.com", "auto", self.db_path)
        with self.assertRaisesRegex(ValueError, "existing account"):
            set_theme_preference("missing@example.com", "Dark", self.db_path)


if __name__ == "__main__":
    unittest.main()
