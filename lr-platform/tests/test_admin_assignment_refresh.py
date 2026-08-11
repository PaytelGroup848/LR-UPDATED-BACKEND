"""Regression tests for Admin Panel assignment refresh."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


ADMIN_DIR = Path(__file__).resolve().parents[1] / 'admin-panel'
if str(ADMIN_DIR) not in sys.path:
    sys.path.insert(0, str(ADMIN_DIR))

from panels.assign_tab import AssignTab


class Value:
    def __init__(self, value=''):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Tree:
    def __init__(self):
        self.rows = []

    def get_children(self):
        return tuple(self.rows)

    def delete(self, *_rows):
        self.rows.clear()

    def insert(self, _parent, _index, values):
        self.rows.append(tuple(values))


class Client:
    apps_data = [
        {'id': 'airtable', 'name': 'Airtable'},
        {'id': 'tally', 'name': 'Tally'},
        {'id': 'code', 'name': 'vs code'},
    ]

    def __init__(self):
        self.assignment_calls = []

    def users(self):
        return [{'id': 'paytel', 'username': 'Paytel'}]

    def apps(self):
        return list(self.apps_data)

    def assignments_for_user(self, user_id):
        self.assignment_calls.append(user_id)
        return {
            'assigned_app_ids': ['tally', 'code'],
            'available_apps': list(self.apps_data),
        }


class AdminAssignmentRefreshTests(unittest.TestCase):
    def test_refresh_reloads_preselected_user(self):
        tab = object.__new__(AssignTab)
        tab.app = type('App', (), {
            'client': Client(),
            'require_login': staticmethod(lambda: True),
        })()
        tab.users, tab.apps, tab.assigned_ids = [], [], set()
        tab.user_var, tab.user_combo = Value('paytel - Paytel'), {}
        tab.assigned_tree, tab.available_tree = Tree(), Tree()

        tab.refresh()

        self.assertEqual(tab.app.client.assignment_calls, ['paytel'])
        self.assertEqual(
            [row[1] for row in tab.assigned_tree.rows],
            ['Tally', 'vs code'],
        )
        self.assertEqual(
            [row[1] for row in tab.available_tree.rows],
            ['Airtable'],
        )

    def test_assignment_ids_are_strings(self):
        self.assertEqual(
            AssignTab._assigned_id_set({'assigned_app_ids': [123]}),
            {'123'},
        )

    @patch('panels.assign_tab.messagebox.showinfo')
    def test_assign_uses_backend_shortcut_sync_only(self, _showinfo):
        tab = object.__new__(AssignTab)
        tab.app = type('App', (), {'client': type('Client', (), {})()})()
        tab.app.client.assign_app = Mock()
        tab.selected_user = Mock(return_value={'id': 'paytel'})
        tab._selected_id = Mock(return_value='airtable')
        tab.available_tree = object()
        tab.load_for_user = Mock()
        tab._sync_user_desktop_shortcut = Mock()

        tab.assign_selected()

        tab.app.client.assign_app.assert_called_once_with('airtable', 'paytel')
        tab._sync_user_desktop_shortcut.assert_not_called()
        tab.load_for_user.assert_called_once_with()

    @patch('panels.assign_tab.messagebox.showinfo')
    def test_unassign_uses_backend_shortcut_sync_only(self, _showinfo):
        tab = object.__new__(AssignTab)
        tab.app = type('App', (), {'client': type('Client', (), {})()})()
        tab.app.client.unassign_app = Mock()
        tab.selected_user = Mock(return_value={'id': 'paytel'})
        tab._selected_id = Mock(return_value='airtable')
        tab.assigned_tree = object()
        tab.load_for_user = Mock()
        tab._sync_user_desktop_shortcut = Mock()

        tab.remove_selected()

        tab.app.client.unassign_app.assert_called_once_with('airtable', 'paytel')
        tab._sync_user_desktop_shortcut.assert_not_called()
        tab.load_for_user.assert_called_once_with()

    def test_managed_shortcut_acl_keeps_privileged_maintenance_access(self):
        root = Path(__file__).resolve().parents[1]
        for relative_path in (
            'agent/services/desktop_shortcut.py',
            'backend/services/desktop_shortcut_service.py',
        ):
            source = (root / relative_path).read_text(encoding='utf-8')
            self.assertIn('Grant-ShortcutMaintenanceAccess', source)
            self.assertIn('*S-1-5-32-544:(F)', source)
            self.assertIn('*S-1-5-18:(F)', source)
            self.assertIn('FileSystemRights]\'ReadAndExecute\'', source)
            self.assertIn('FileSystemRights]\'FullControl\'', source)

    def test_shortcuts_use_registered_windows_profile(self):
        root = Path(__file__).resolve().parents[1]
        for relative_path in (
            'agent/services/desktop_shortcut.py',
            'backend/services/desktop_shortcut_service.py',
        ):
            source = (root / relative_path).read_text(encoding='utf-8')
            self.assertIn('Resolve-UserProfilePath', source)
            self.assertIn('Microsoft\\Windows NT\\CurrentVersion\\ProfileList', source)
            self.assertIn('$profileDesktop = Join-Path $profilePath \'Desktop\'', source)
            self.assertNotIn('Join-Path (Join-Path \'C:\\Users\' $username) \'Desktop\'', source)

    def test_published_shortcuts_use_published_working_directory_and_icon(self):
        root = Path(__file__).resolve().parents[1]
        for relative_path in (
            'agent/services/desktop_shortcut.py',
            'backend/services/desktop_shortcut_service.py',
        ):
            source = (root / relative_path).read_text(encoding='utf-8')
            self.assertIn('$sourceWorkingDirectory = Split-Path -Parent $sourceTargetPath', source)
            self.assertIn('$workingDirectory = Split-Path -Parent $targetPath', source)
            self.assertIn('$iconPath = $targetPath', source)

    def test_agent_heartbeat_survives_reconnect_window(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / 'agent/main.py').read_text(encoding='utf-8')
        self.assertIn('ensure_heartbeat_thread()', source)
        self.assertIn('while True:', source)
        self.assertIn('if sio.connected and NAMESPACE in', source)
        self.assertNotIn('while sio.connected:', source)


if __name__ == '__main__':
    unittest.main()
