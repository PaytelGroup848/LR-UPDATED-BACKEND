import sys
import unittest
from pathlib import Path


ADMIN_PANEL_DIR = Path(__file__).resolve().parents[1] / "admin-panel"
if str(ADMIN_PANEL_DIR) not in sys.path:
    sys.path.insert(0, str(ADMIN_PANEL_DIR))

from panels.assign_tab import AssignTab


class AdminAssignmentTargetTests(unittest.TestCase):
    def test_remote_app_file_path_is_used_for_desktop_shortcut(self):
        target = AssignTab._app_target({
            "remote_app_file_path": r"C:\Program Files\Microsoft VS Code\Code.exe",
            "remote_app_program": "||vs-code",
        })

        self.assertEqual(target, r"C:\Program Files\Microsoft VS Code\Code.exe")

    def test_legacy_initial_program_remains_supported(self):
        target = AssignTab._app_target({
            "initial_program": r"C:\Tally\tally.exe",
        })

        self.assertEqual(target, r"C:\Tally\tally.exe")

    def test_remote_app_alias_is_not_used_as_a_filesystem_target(self):
        target = AssignTab._app_target({"remote_app_program": "||airtable"})

        self.assertEqual(target, "")


if __name__ == "__main__":
    unittest.main()
