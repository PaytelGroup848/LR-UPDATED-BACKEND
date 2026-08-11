import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ADMIN_PANEL_DIR = Path(__file__).resolve().parents[1] / "admin-panel"
if str(ADMIN_PANEL_DIR) not in sys.path:
    sys.path.insert(0, str(ADMIN_PANEL_DIR))

import windows_account


class AdminWindowsAccountDeletionTests(unittest.TestCase):
    @patch("windows_account.platform.system", return_value="Windows")
    @patch("windows_account._run_delete_script")
    def test_deletes_lr_managed_windows_account(self, run_delete, _system):
        run_delete.return_value = SimpleNamespace(returncode=0, stdout="", stderr="")

        deleted, message = windows_account.delete_windows_user("alice")

        self.assertTrue(deleted)
        self.assertEqual(message, "Windows account deleted")
        run_delete.assert_called_once_with(
            "alice",
            windows_account.MANAGED_ACCOUNT_DESCRIPTION,
        )

    @patch("windows_account.platform.system", return_value="Windows")
    @patch("windows_account._run_delete_script")
    def test_missing_windows_account_is_idempotent_success(self, run_delete, _system):
        run_delete.return_value = SimpleNamespace(returncode=11, stdout="", stderr="")

        deleted, message = windows_account.delete_windows_user("alice")

        self.assertTrue(deleted)
        self.assertEqual(message, "Windows account was already absent")

    @patch("windows_account.platform.system", return_value="Windows")
    @patch("windows_account._run_delete_script")
    def test_refuses_non_lr_windows_account(self, run_delete, _system):
        run_delete.return_value = SimpleNamespace(returncode=13, stdout="", stderr="")

        deleted, message = windows_account.delete_windows_user("shared-rdp")

        self.assertFalse(deleted)
        self.assertIn("not created by LR Remote Access", message)

    @patch("windows_account.platform.system", return_value="Windows")
    @patch("windows_account._run_delete_script")
    def test_refuses_protected_windows_account(self, run_delete, _system):
        run_delete.return_value = SimpleNamespace(returncode=12, stdout="", stderr="")

        deleted, message = windows_account.delete_windows_user("Administrator")

        self.assertFalse(deleted)
        self.assertIn("Protected Windows system accounts", message)


class AdminWindowsAccountIdentityTests(unittest.TestCase):
    @patch("windows_account.platform.system", return_value="Windows")
    @patch("windows_account._run_identity_script")
    def test_domain_controller_account_uses_computer_domain(self, run_identity, _system):
        run_identity.return_value = SimpleNamespace(
            returncode=0,
            stdout='{"scope":"domain","domain":"MYCOMPANY"}',
            stderr="",
        )

        identity = windows_account.resolve_windows_account_identity("Cloudedata")

        self.assertEqual(
            identity,
            {"scope": "domain", "domain": "MYCOMPANY"},
        )

    @patch("windows_account.platform.system", return_value="Windows")
    @patch("windows_account._run_identity_script")
    def test_standalone_account_keeps_local_scope(self, run_identity, _system):
        run_identity.return_value = SimpleNamespace(
            returncode=0,
            stdout='{"scope":"local","domain":""}',
            stderr="",
        )

        identity = windows_account.resolve_windows_account_identity("alice")

        self.assertEqual(identity, {"scope": "local", "domain": ""})


if __name__ == "__main__":
    unittest.main()
