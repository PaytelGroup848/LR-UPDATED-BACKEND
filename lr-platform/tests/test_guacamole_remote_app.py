import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

from backend.manager.guacamole_manager import GuacamoleClient


class GuacamoleRemoteAppTests(unittest.TestCase):
    @patch("backend.manager.guacamole_manager.requests.post")
    def test_twenty_five_parallel_launches_share_one_admin_login(self, post):
        token_response = Mock(status_code=200)
        token_response.json.return_value = {"authToken": "admin-token"}
        post.return_value = token_response
        client = GuacamoleClient("http://guacamole/guacamole", "guacadmin", "secret")

        with ThreadPoolExecutor(max_workers=25) as pool:
            tokens = list(pool.map(lambda _index: client.get_admin_token(), range(25)))

        self.assertEqual(tokens, ["admin-token"] * 25)
        self.assertEqual(post.call_count, 1)

    @patch("backend.manager.guacamole_manager.requests.post")
    def test_remote_app_uses_guacamole_rail_parameters(self, post):
        token_response = Mock(status_code=200)
        token_response.json.return_value = {"authToken": "admin-token"}
        create_response = Mock(status_code=201)
        create_response.json.return_value = {"identifier": "56"}
        post.side_effect = [token_response, create_response]

        client = GuacamoleClient(
            base_url="http://guacamole/guacamole",
            public_url="http://localhost:8080/guacamole",
            username="guacadmin",
            password="secret",
        )
        result = client.create_rdp_connection(
            name="Calculator",
            host="10.0.0.10",
            rdp_username="student",
            rdp_password="password",
            app={
                "name": "Calculator",
                "display_mode": "remote_app",
                "launch_mode": "remote_app",
                "remote_app_program": "||calculator",
                "working_directory": r"C:\\Windows\\System32",
                "arguments": "/example",
            },
            require_remote_app=True,
        )

        self.assertTrue(result["success"])
        payload = post.call_args_list[1].kwargs["json"]
        parameters = payload["parameters"]
        self.assertEqual(parameters["remote-app"], "||calculator")
        self.assertEqual(parameters["remote-app-dir"], r"C:\\Windows\\System32")
        self.assertEqual(parameters["remote-app-args"], "/example")
        self.assertNotIn("remote-app-program", parameters)
        self.assertNotIn("remote-app-name", parameters)
        self.assertEqual(parameters["color-depth"], "24")
        self.assertEqual(parameters["enable-wallpaper"], "false")
        self.assertEqual(parameters["disable-bitmap-caching"], "false")
        self.assertEqual(parameters["disable-gfx"], "false")
        self.assertEqual(parameters["force-lossless"], "false")
        self.assertEqual(parameters["disable-audio"], "false")
        self.assertEqual(parameters["enable-printing"], "true")
        self.assertEqual(parameters["printer-name"], "LR Remote Printer")

    @patch("backend.manager.guacamole_manager.requests.post")
    def test_full_desktop_launch_does_not_send_rail_parameters(self, post):
        token_response = Mock(status_code=200)
        token_response.json.return_value = {"authToken": "admin-token"}
        create_response = Mock(status_code=201)
        create_response.json.return_value = {"identifier": "58"}
        post.side_effect = [token_response, create_response]

        client = GuacamoleClient(
            base_url="http://guacamole/guacamole",
            public_url="http://localhost:8080/guacamole",
            username="guacadmin",
            password="secret",
        )
        result = client.create_rdp_connection(
            name="Desktop",
            host="10.0.0.10",
            app={
                "name": "Desktop",
                "display_mode": "full_desktop",
                "launch_mode": "desktop",
                "initial_program": "explorer.exe",
            },
        )

        self.assertTrue(result["success"])
        parameters = post.call_args_list[1].kwargs["json"]["parameters"]
        self.assertNotIn("remote-app", parameters)
        self.assertNotIn("initial-program", parameters)
        self.assertNotIn("remote-app-dir", parameters)
        self.assertNotIn("remote-app-args", parameters)

    @patch("backend.manager.guacamole_manager.requests.post")
    def test_initial_program_remote_app_payload_is_sent_for_initial_program_launch(self, post):
        token_response = Mock(status_code=200)
        token_response.json.return_value = {"authToken": "admin-token"}
        create_response = Mock(status_code=201)
        create_response.json.return_value = {"identifier": "59"}
        post.side_effect = [token_response, create_response]

        client = GuacamoleClient(
            base_url="http://guacamole/guacamole",
            public_url="http://localhost:8080/guacamole",
            username="guacadmin",
            password="secret",
        )
        result = client.create_rdp_connection(
            name="Shell",
            host="10.0.0.10",
            app={
                "name": "Shell",
                "display_mode": "remote_app",
                "launch_mode": "initial_program",
                "initial_program": r"C:\\Tally\\tally.exe",
                "working_directory": r"C:\\Tally",
                "arguments": "/example",
            },
        )

        self.assertTrue(result["success"])
        parameters = post.call_args_list[1].kwargs["json"]["parameters"]
        self.assertEqual(parameters["initial-program"], r"C:\\Tally\\tally.exe")
        self.assertEqual(parameters["remote-app-dir"], r"C:\\Tally")
        self.assertEqual(parameters["remote-app-args"], "/example")
        self.assertNotIn("remote-app", parameters)
        self.assertNotIn("remote-app-program", parameters)
        self.assertNotIn("remote-app-name", parameters)

    @patch("backend.manager.guacamole_manager.requests.post")
    def test_virtual_printer_can_be_disabled(self, post):
        token_response = Mock(status_code=200)
        token_response.json.return_value = {"authToken": "admin-token"}
        create_response = Mock(status_code=201)
        create_response.json.return_value = {"identifier": "56"}
        post.side_effect = [token_response, create_response]
        client = GuacamoleClient(
            "http://guacamole/guacamole",
            "guacadmin",
            "secret",
            enable_printing=False,
        )

        self.assertTrue(client.create_rdp_connection("Desktop", "10.0.0.10")["success"])
        parameters = post.call_args_list[1].kwargs["json"]["parameters"]
        self.assertEqual(parameters["enable-printing"], "false")

    @patch("backend.manager.guacamole_manager.requests.post")
    def test_performance_profile_reduces_bandwidth(self, post):
        token_response = Mock(status_code=200)
        token_response.json.return_value = {"authToken": "admin-token"}
        create_response = Mock(status_code=201)
        create_response.json.return_value = {"identifier": "57"}
        post.side_effect = [token_response, create_response]
        client = GuacamoleClient(
            "http://guacamole/guacamole",
            "guacadmin",
            "secret",
            visual_quality="performance",
        )

        self.assertTrue(client.create_rdp_connection("Desktop", "10.0.0.10")["success"])
        parameters = post.call_args_list[1].kwargs["json"]["parameters"]
        self.assertEqual(parameters["color-depth"], "16")
        self.assertEqual(parameters["enable-desktop-composition"], "false")
        self.assertEqual(parameters["disable-gfx"], "false")

    @patch("backend.manager.guacamole_manager.requests.post")
    def test_admin_token_is_reused_for_launch_bursts(self, post):
        token_response = Mock(status_code=200)
        token_response.json.return_value = {"authToken": "admin-token"}
        first_create = Mock(status_code=201)
        first_create.json.return_value = {"identifier": "56"}
        second_create = Mock(status_code=201)
        second_create.json.return_value = {"identifier": "57"}
        post.side_effect = [token_response, first_create, second_create]
        client = GuacamoleClient("http://guacamole/guacamole", "guacadmin", "secret")

        self.assertTrue(client.create_rdp_connection("One", "10.0.0.10")["success"])
        self.assertTrue(client.create_rdp_connection("Two", "10.0.0.10")["success"])
        self.assertEqual(post.call_count, 3)

    @patch("backend.manager.guacamole_manager.requests.post")
    def test_required_remote_app_rejects_missing_program(self, post):
        token_response = Mock(status_code=200)
        token_response.json.return_value = {"authToken": "admin-token"}
        post.return_value = token_response

        client = GuacamoleClient(
            base_url="http://guacamole/guacamole",
            username="guacadmin",
            password="secret",
        )
        result = client.create_rdp_connection(
            name="Missing app",
            host="10.0.0.10",
            app={"display_mode": "remote_app", "launch_mode": "remote_app"},
            require_remote_app=True,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "RemoteApp program is required")
        self.assertEqual(post.call_count, 1)


if __name__ == "__main__":
    unittest.main()
