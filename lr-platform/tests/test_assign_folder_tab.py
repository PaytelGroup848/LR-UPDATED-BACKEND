import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add admin-panel to sys.path for importing AssignFolderTab
admin_panel_dir = str(Path(__file__).resolve().parents[1] / "admin-panel")
if admin_panel_dir not in sys.path:
    sys.path.insert(0, admin_panel_dir)

from panels.assign_folder_tab import AssignFolderTab


class TestAssignFolderTab(unittest.TestCase):
    def test_selected_user_parses_user_id_from_label(self):
        tab = AssignFolderTab.__new__(AssignFolderTab)
        tab.users = [
            {"id": "usr-123", "username": "Nick"},
            {"id": "usr-456", "username": "Admin"},
        ]
        tab.user_var = MagicMock()
        tab.user_var.get.return_value = "usr-123 - Nick"

        selected = tab.selected_user()
        self.assertIsNotNone(selected)
        self.assertEqual(selected["id"], "usr-123")
        self.assertEqual(selected["username"], "Nick")

    def test_selected_server_parses_server_id_from_label(self):
        tab = AssignFolderTab.__new__(AssignFolderTab)
        tab.servers = [
            {"id": "srv-999", "name": "WIN-SERVER", "host": "10.0.0.1"},
        ]
        tab.server_var = MagicMock()
        tab.server_var.get.return_value = "srv-999 - WIN-SERVER (10.0.0.1)"

        selected = tab.selected_server()
        self.assertIsNotNone(selected)
        self.assertEqual(selected["id"], "srv-999")

    @patch("panels.assign_folder_tab.messagebox")
    def test_assign_folder_from_form_uses_selected_tree_folder_if_path_empty(self, mock_msg):
        tab = AssignFolderTab.__new__(AssignFolderTab)
        tab.users = [{"id": "usr-100", "username": "John"}]
        tab.user_var = MagicMock()
        tab.user_var.get.return_value = "usr-100 - John"

        tab.apps = [
            {
                "id": "fld-555",
                "item_type": "folder",
                "folder_path": r"C:\Data\Shared",
                "folder_permission": "read",
            }
        ]

        tab._selected_id = MagicMock(return_value="fld-555")
        tab.available_tree = MagicMock()
        tab.path_var = MagicMock()
        tab.path_var.get.return_value = ""
        tab.name_var = MagicMock()

        tab.app = MagicMock()
        tab.app.client.assign_app.return_value = {"success": True}
        tab.load_for_user = MagicMock()

        tab.assign_folder_from_form()
        tab.app.client.assign_app.assert_called_once_with("fld-555", "usr-100")
        mock_msg.showinfo.assert_called_once_with("Assign Folder", "Folder assigned")


if __name__ == "__main__":
    unittest.main()
