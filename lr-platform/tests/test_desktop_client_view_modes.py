import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch


DESKTOP_CLIENT_DIR = Path(__file__).resolve().parents[1] / "desktop-client"
if str(DESKTOP_CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(DESKTOP_CLIENT_DIR))

from launcher.login_window import LoginWindowMixin, VIEW_MODE_OPTIONS, VIEW_MODE_VALUES
from session.app_window import AppWindowMixin


class DesktopClientViewModeTests(unittest.TestCase):
    def test_login_exposes_both_required_connection_choices(self):
        self.assertEqual(VIEW_MODE_OPTIONS, ("Desktop View", "Remote App View"))
        self.assertEqual(VIEW_MODE_VALUES["Desktop View"], "rdp_desktop")
        self.assertEqual(VIEW_MODE_VALUES["Remote App View"], "rdp_remote_app")

    def test_login_selector_has_only_two_native_rdp_modes(self):
        client = LoginWindowMixin()
        client.view_mode_var = Mock()
        client.view_mode_help = None

        client._set_view_mode("Desktop View")
        client.view_mode_var.set.assert_called_with("rdp_desktop")

        client._set_view_mode("Remote App View")
        client.view_mode_var.set.assert_called_with("rdp_remote_app")

        client._set_view_mode("Web View")
        client.view_mode_var.set.assert_called_with("rdp_desktop")

    def test_desktop_login_checks_license_then_launches_native_desktop(self):
        client = self._login_client("rdp_desktop")
        login_result = {
            "success": True,
            "user": {"username": "alice"},
            "launch_endpoint": "/api/lr/desktop",
        }
        desktop_result = {
            "success": True,
            "rdp_file_url": "/portal/api/sessions/session-id/rdp-file",
            "server_name": "Main Server",
        }
        client.api.post_json.side_effect = [login_result, desktop_result]
        client.api.get_json.return_value = {"status": "TRIAL_ACTIVE", "blocked": False}
        client.open_desktop_login_response = Mock()

        client._login("alice", "secret")

        self.assertEqual(client.api.post_json.call_args_list, [
            call("/login", {
                "username": "alice",
                "password": "secret",
                "connection_type": "desktop",
            }),
            call("/api/lr/desktop", {}),
        ])
        client.api.get_json.assert_called_once_with("/license/me")
        callback = client.root.after.call_args.args[1]
        callback()
        client.open_desktop_login_response.assert_called_once_with(desktop_result)

    def test_remote_app_login_checks_license_then_lists_assigned_apps(self):
        client = self._login_client("rdp_remote_app")
        client.api.post_json.return_value = {
            "success": True,
            "user": {"username": "alice"},
            "resources_url": "/api/lr/my-resources",
        }
        client.api.get_json.side_effect = [
            {"status": "LICENSED", "blocked": False},
            {
                "success": True,
                "applications": [{"id": "app-id", "name": "Calculator"}],
                "folders": [{"id": "folder-id", "name": "Nikhil (Read)", "type": "folder"}],
            },
        ]
        client.show_apps = Mock()

        client._login("alice", "secret")

        client.api.post_json.assert_called_once_with("/login", {
            "username": "alice",
            "password": "secret",
            "connection_type": "remoteapp",
        })
        self.assertEqual(client.api.get_json.call_args_list, [
            call("/license/me"),
            call("/api/lr/my-resources"),
        ])
        callback = client.root.after.call_args.args[1]
        callback()
        client.show_apps.assert_called_once_with(
            [
                {"id": "app-id", "name": "Calculator"},
                {"id": "folder-id", "name": "Nikhil (Read)", "type": "folder"},
            ]
        )

    def test_company_code_is_sent_with_desktop_login(self):
        client = self._login_client("rdp_desktop")
        client.api.post_json.side_effect = [
            {"success": True, "user": {"username": "user1"}},
            {
                "success": True,
                "rdp_file_url": "/session.rdp",
                "server_name": "Company A Server",
            },
        ]
        client.api.get_json.return_value = {"status": "LICENSED", "blocked": False}
        client.open_desktop_login_response = Mock()

        client._login("user1", "secret", "company-a")

        self.assertEqual(client.api.post_json.call_args_list[0], call("/login", {
            "username": "user1",
            "password": "secret",
            "connection_type": "desktop",
            "company_code": "company-a",
        }))

    @patch("launcher.login_window.messagebox.showwarning")
    def test_expired_trial_shows_admin_contact_message_without_key_popup(self, showwarning):
        client = self._login_client("rdp_desktop")
        client.api.post_json.return_value = {
            "success": True,
            "user": {"username": "alice"},
        }
        license_info = {
            "status": "TRIAL_EXPIRED",
            "blocked": True,
            "message": "Your 7 day trial has ended.",
        }
        client.api.get_json.return_value = license_info

        client._login("alice", "secret")

        client.api.post_json.assert_called_once()
        callback = client.root.after.call_args.args[1]
        callback()
        showwarning.assert_called_once_with(
            "LR Remote Access",
            "Your 7 day trial has ended.",
        )
        client.status.configure.assert_called_once_with(
            text="License activation required",
            text_color="#dc2626",
        )

    @patch("session.app_window.os.startfile")
    def test_desktop_response_opens_full_desktop_rdp_file(self, startfile):
        client = self._app_client()
        client._download_rdp_file = Mock(return_value=r"C:\Temp\Main_Server.rdp")

        client.open_desktop_login_response({
            "rdp_file_url": "/portal/api/sessions/session-id/rdp-file",
            "server_id": "server-id",
            "server_name": "Main Server",
        })

        client._download_rdp_file.assert_called_once_with(
            "/portal/api/sessions/session-id/rdp-file",
            {"id": "server-id", "name": "Main Server"},
        )
        startfile.assert_called_once_with(r"C:\Temp\Main_Server.rdp")

    @patch("session.app_window.os.startfile")
    def test_remote_app_card_directly_uses_native_remoteapp_endpoint(self, startfile):
        client = self._app_client()
        client.api.post_json.return_value = {"rdp_file_url": "/remote-app.rdp"}
        client._download_rdp_file = Mock(return_value=r"C:\Temp\remote-app.rdp")
        client.launch_app = Mock()
        app = {"id": "app-id", "name": "Calculator"}

        client.open_application(app)
        client.launch_app.assert_called_once_with(app)

        client.launch_app = AppWindowMixin.launch_app.__get__(client, AppWindowMixin)
        client.run_async = lambda target: target()
        client._launch_app(app)

        client.api.post_json.assert_called_once_with(
            "/api/lr/launch",
            {"resource_id": "app-id", "type": "application"},
        )
        startfile.assert_called_once_with(r"C:\Temp\remote-app.rdp")

    def test_remote_app_refresh_uses_only_native_resource_endpoint(self):
        client = self._app_client()
        client.api.get_json.return_value = {
            "applications": [{"id": "app-id", "name": "Calculator"}],
            "folders": [{"id": "folder-id", "name": "Nikhil (Read)", "type": "folder"}],
        }
        client.show_apps = Mock()

        client._reload_apps()

        client.api.get_json.assert_called_once_with("/api/lr/my-resources")
        callback = client.root.after.call_args.args[1]
        callback()
        client.show_apps.assert_called_once_with([
            {"id": "app-id", "name": "Calculator"},
            {"id": "folder-id", "name": "Nikhil (Read)", "type": "folder"},
        ])

    def test_remote_app_view_uses_compact_top_right_panel_geometry(self):
        panel_height, list_height, geometry = AppWindowMixin._floating_panel_layout(
            2,
            1920,
            1080,
        )

        self.assertEqual(panel_height, 360)
        self.assertEqual(list_height, 124)
        self.assertEqual(geometry, "320x360+1582+48")

    def test_floating_panel_caps_visible_rows_and_fits_short_screen(self):
        panel_height, list_height, geometry = AppWindowMixin._floating_panel_layout(
            10,
            1366,
            400,
        )

        self.assertEqual(panel_height, 320)
        self.assertEqual(list_height, 84)
        self.assertEqual(geometry, "320x320+1028+48")

    def test_folder_resource_uses_folder_icon(self):
        glyph, color = AppWindowMixin._app_icon({
            "name": "Desktop folder",
            "type": "folder",
        })

        self.assertEqual(glyph, "▰")
        self.assertEqual(color, "#e6a817")

    @patch("session.app_window.os.startfile")
    def test_folder_card_launches_with_folder_resource_type(self, _startfile):
        client = self._app_client()
        client.api.post_json.return_value = {"rdp_file_url": "/folder.rdp"}
        client._download_rdp_file = Mock(return_value=r"C:\Temp\folder.rdp")

        client._launch_app({"id": "folder-id", "name": "Nikhil (Read)", "type": "folder"})

        client.api.post_json.assert_called_once_with(
            "/api/lr/launch",
            {"resource_id": "folder-id", "type": "folder"},
        )

    @staticmethod
    def _login_client(mode):
        client = LoginWindowMixin()
        client.view_mode_var = Mock()
        client.view_mode_var.get.return_value = mode
        client.api = Mock()
        client.root = Mock()
        client.status = Mock()
        return client

    @staticmethod
    def _app_client():
        client = AppWindowMixin()
        client.api = Mock()
        client.root = Mock()
        client.status = Mock()
        return client


if __name__ == "__main__":
    unittest.main()
