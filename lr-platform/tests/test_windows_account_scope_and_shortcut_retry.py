import unittest
from unittest.mock import Mock, patch

from backend.services.portal_service import (
    _guacamole_windows_identity,
    _rdp_identity_for_user,
)
from backend.services.windows_account_service import WindowsAccountService
from backend.sockets import agent_socket


class WindowsAccountScopeTests(unittest.TestCase):
    @patch(
        "backend.services.windows_account_service.encrypt_secret",
        return_value="encrypted-secret",
    )
    def test_precreated_local_account_drops_domain(self, _encrypt):
        updates, error = WindowsAccountService.build_updates(
            {
                "windows_username": "Cloudedata",
                "windows_password": "secret",
                "windows_domain": "MYCOMPANY",
                "windows_account_scope": "local",
                "windows_account_enabled": True,
            },
            default_username="Cloudedata",
            default_password="secret",
            create_local_account=False,
        )

        self.assertIsNone(error)
        self.assertEqual(updates["windows_account_scope"], "local")
        self.assertIsNone(updates["windows_domain"])

    @patch(
        "backend.services.windows_account_service.WindowsAccountService.create_local_user",
        return_value={
            "success": True,
            "message": "Windows account created",
            "windows_account_scope": "domain",
            "windows_domain": "MYCOMPANY",
        },
    )
    @patch(
        "backend.services.windows_account_service.encrypt_secret",
        return_value="encrypted-secret",
    )
    def test_domain_controller_provisioning_overrides_local_default(
        self,
        _encrypt,
        _create_local_user,
    ):
        updates, error = WindowsAccountService.build_updates(
            {
                "windows_username": "Cloudedata",
                "windows_password": "secret",
                "windows_account_enabled": True,
            },
            default_username="Cloudedata",
            default_password="secret",
            create_local_account=True,
        )

        self.assertIsNone(error)
        self.assertEqual(updates["windows_account_scope"], "domain")
        self.assertEqual(updates["windows_domain"], "MYCOMPANY")

    @patch("backend.services.portal_service.decrypt_secret", return_value="secret")
    def test_local_account_never_inherits_server_domain(self, _decrypt):
        identity = _rdp_identity_for_user(
            {
                "username": "Cloudedata",
                "windows_username": "Cloudedata",
                "windows_password": "encrypted",
                "windows_account_scope": "local",
            },
            {"domain": "MYCOMPANY", "hostname": "WIN-SERVER"},
        )

        self.assertEqual(identity["username"], r".\Cloudedata")
        self.assertEqual(identity["domain"], "")

    @patch("backend.services.portal_service.decrypt_secret", return_value="secret")
    def test_domain_account_keeps_configured_domain(self, _decrypt):
        identity = _rdp_identity_for_user(
            {
                "username": "alice",
                "windows_username": "alice",
                "windows_password": "encrypted",
                "windows_domain": "MYCOMPANY",
                "windows_account_scope": "domain",
            },
            {"domain": "OTHER"},
        )

        self.assertEqual(identity["username"], "alice")
        self.assertEqual(identity["domain"], "MYCOMPANY")

    def test_guacamole_splits_local_prefix_and_uses_agent_hostname(self):
        username, domain = _guacamole_windows_identity(
            r".\User3",
            "",
            {"agent_hostname": "WIN-CLOUD87VM46", "host": "191.44.87.46"},
        )

        self.assertEqual(username, "User3")
        self.assertEqual(domain, "WIN-CLOUD87VM46")

    def test_guacamole_splits_domain_prefix(self):
        username, domain = _guacamole_windows_identity(
            r"MYCOMPANY\alice",
            "",
            {},
        )

        self.assertEqual(username, "alice")
        self.assertEqual(domain, "MYCOMPANY")


class ShortcutRetryTests(unittest.TestCase):
    def setUp(self):
        agent_socket._shortcut_retry_last_at.clear()
        agent_socket._shortcut_retry_inflight.clear()
        agent_socket.connected_agents.clear()

    def tearDown(self):
        agent_socket._shortcut_retry_last_at.clear()
        agent_socket._shortcut_retry_inflight.clear()
        agent_socket.connected_agents.clear()

    @patch.object(agent_socket.socketio, "start_background_task")
    @patch.object(agent_socket, "monotonic", side_effect=[100, 110, 131])
    def test_shortcut_retry_is_throttled_per_agent(self, _clock, start_task):
        self.assertTrue(
            agent_socket._schedule_pending_shortcut_sync("sid-1", "agent-1")
        )
        agent_socket._shortcut_retry_inflight.discard("sid-1")

        self.assertFalse(
            agent_socket._schedule_pending_shortcut_sync("sid-1", "agent-1")
        )
        self.assertTrue(
            agent_socket._schedule_pending_shortcut_sync("sid-1", "agent-1")
        )

        self.assertEqual(start_task.call_count, 2)

    @patch.object(agent_socket, "_schedule_pending_shortcut_sync")
    @patch.object(agent_socket.AgentPresenceService, "heartbeat")
    @patch.object(agent_socket, "update_heartbeat", side_effect=RuntimeError("db down"))
    def test_heartbeat_does_not_raise_when_db_update_fails(self, update, heartbeat, schedule):
        agent_socket.connected_agents["sid-1"] = {
            "agent_id": "agent-1",
            "status": "online",
        }

        agent_socket.handle_heartbeat({"agent_id": "agent-1"})

        update.assert_called_once_with("agent-1")
        heartbeat.assert_called_once()
        schedule.assert_called_once_with("sid-1", "agent-1")

    @patch.object(agent_socket, "_schedule_pending_shortcut_sync")
    @patch.object(agent_socket, "update_heartbeat")
    def test_heartbeat_schedules_pending_shortcut_retry(self, update, schedule):
        agent_socket.connected_agents["sid-1"] = {
            "agent_id": "agent-1",
            "status": "online",
        }

        agent_socket.handle_heartbeat({"agent_id": "agent-1"})

        update.assert_called_once_with("agent-1")
        schedule.assert_called_once_with("sid-1", "agent-1")

    @patch.object(
        agent_socket.socketio,
        "start_background_task",
        side_effect=RuntimeError("cannot start"),
    )
    def test_failed_task_start_does_not_block_future_retries(self, _start_task):
        with self.assertRaisesRegex(RuntimeError, "cannot start"):
            agent_socket._schedule_pending_shortcut_sync(
                "sid-1",
                "agent-1",
                force=True,
            )

        self.assertNotIn("sid-1", agent_socket._shortcut_retry_inflight)


class AgentDisconnectPresenceTests(unittest.TestCase):
    def tearDown(self):
        agent_socket.connected_agents.clear()

    @patch.object(agent_socket, "set_offline")
    @patch.object(agent_socket, "remove_sid", return_value=[])
    @patch.object(agent_socket, "_request_sid", return_value="old-sid")
    @patch.object(agent_socket.AgentPresenceService, "remove")
    @patch.object(
        agent_socket.AgentPresenceService,
        "get_server",
        return_value={"connection_id": "new-sid"},
    )
    def test_old_disconnect_does_not_mark_reconnected_agent_offline(
        self,
        _get_server,
        _remove_presence,
        _request_sid,
        _remove_sid,
        set_offline,
    ):
        agent_socket.connected_agents["old-sid"] = {
            "agent_id": "agent-1",
            "tenant_id": "tenant-1",
            "server_id": "server-1",
            "connection_id": "old-sid",
        }

        agent_socket.handle_agent_disconnect()

        set_offline.assert_not_called()


if __name__ == "__main__":
    unittest.main()
