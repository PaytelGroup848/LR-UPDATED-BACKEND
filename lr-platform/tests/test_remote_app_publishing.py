import json
import unittest
from unittest.mock import Mock, patch

from backend.services.agent_command_service import AgentCommandService
from backend.services.apps_service import ApplicationService
from backend.services.lr_resources_service import _is_published_folder, _is_published_remote_app
from backend.services.remote_app_service import RemoteAppService
from shared.windows.remote_app import _REMOTE_APP_SCRIPT, run_remote_app_action


class RemoteAppFieldTests(unittest.TestCase):
    def test_executable_path_generates_stable_rdp_alias(self):
        fields = RemoteAppService.normalize_app_fields({
            "name": "Tally Prime",
            "remote_app_file_path": r"C:\Program Files\TallyPrime\TallyPrime.exe",
        })

        self.assertEqual(fields["remote_app_alias"], "tally-prime")
        self.assertEqual(fields["remote_app_program"], "||tally-prime")
        self.assertEqual(
            fields["remote_app_file_path"],
            r"C:\Program Files\TallyPrime\TallyPrime.exe",
        )
        self.assertEqual(fields["launch_mode"], "remote_app")

    def test_display_name_edit_keeps_existing_alias(self):
        existing = {
            "name": "Tally Prime",
            "remote_app_alias": "tally",
            "remote_app_program": "||tally",
            "remote_app_file_path": r"C:\Tally\tally.exe",
        }

        fields = RemoteAppService.normalize_app_fields(
            {"name": "TallyPrime 6"}, existing=existing
        )

        self.assertEqual(fields["remote_app_alias"], "tally")
        self.assertEqual(fields["remote_app_program"], "||tally")

    def test_pending_or_failed_app_is_hidden_from_remote_app_view(self):
        base = {"item_type": "remote_app", "remote_app_program": "||calculator"}

        self.assertTrue(_is_published_remote_app(base))
        self.assertTrue(_is_published_remote_app({**base, "remote_app_publish_status": "published"}))
        self.assertTrue(_is_published_remote_app({**base, "remote_app_publish_status": "pending"}))
        self.assertFalse(_is_published_remote_app({**base, "remote_app_publish_status": "unpublished"}))

    def test_folder_is_normalized_and_visible_after_rds_publication(self):
        fields = RemoteAppService.normalize_app_fields({
            "name": "Nikhil (Read)",
            "item_type": "folder",
            "initial_program": "explorer.exe",
            "folder_path": r"C:\Users\Administrator\Desktop\Nikhil",
            "arguments": r"C:\Users\Administrator\Desktop\Nikhil",
        })

        self.assertEqual(fields["remote_app_file_path"], "explorer.exe")
        self.assertTrue(fields["remote_app_program"].startswith("||"))
        self.assertTrue(_is_published_folder({
            **fields,
            "item_type": "folder",
            "remote_app_publish_status": "published",
        }))

    def test_folder_without_initial_program_defaults_to_explorer(self):
        fields = RemoteAppService.normalize_app_fields({
            "name": "Shared Docs",
            "item_type": "folder",
            "folder_path": r"C:\Data\SharedDocs",
        })

        self.assertEqual(fields["remote_app_file_path"], "explorer.exe")
        self.assertEqual(fields["initial_program"], "explorer.exe")
        self.assertEqual(fields["arguments"], r"C:\Data\SharedDocs")
        self.assertEqual(fields["item_type"], "folder")

    @patch.object(RemoteAppService, "_windows_agent_candidates")
    def test_multiple_agents_are_matched_to_the_selected_server(self, candidates):
        candidates.return_value = [
            ("sid-one", {"hostname": "RDS-ONE", "ip_address": "10.0.0.1"}),
            ("sid-two", {"hostname": "RDS-TWO", "ip_address": "10.0.0.2"}),
        ]
        spec = {"agent_id": "", "server": {"name": "RDS-TWO", "host": "10.0.0.2"}}

        sid, error = RemoteAppService._agent_sid_for_spec(spec)

        self.assertEqual(sid, "sid-two")
        self.assertIsNone(error)

    @patch.object(RemoteAppService, "_windows_agent_candidates")
    def test_ambiguous_agents_require_explicit_mapping(self, candidates):
        candidates.return_value = [
            ("sid-one", {"hostname": "RDS-ONE", "ip_address": "10.0.0.1"}),
            ("sid-two", {"hostname": "RDS-TWO", "ip_address": "10.0.0.2"}),
        ]

        sid, error = RemoteAppService._agent_sid_for_spec(
            {"agent_id": "", "server": {"name": "Unmatched", "host": "10.0.0.9"}}
        )

        self.assertIsNone(sid)
        self.assertIn("Configure", error)

    @patch("backend.services.remote_app_service.AgentCommandService.call_server")
    def test_publish_routes_through_exact_redis_backed_server_room(self, call_server):
        call_server.return_value = {
            "success": True,
            "status": "published",
            "file_path": r"C:\Program Files\LR RemoteApps\airtable\Airtable.exe",
        }
        spec = {
            "tenant_id": "tenant-paytel",
            "server_id": "server-46",
            "alias": "airtable-paytel",
            "payload": {"action": "publish", "alias": "airtable-paytel"},
            "server": {"_id": "server-46"},
        }

        result = RemoteAppService._dispatch(spec)

        self.assertTrue(result["success"])
        self.assertEqual(result["transport"], "agent_command")
        call_server.assert_called_once_with(
            "sync_remote_app",
            spec["payload"],
            tenant_id="tenant-paytel",
            server_id="server-46",
            timeout=60,
        )

    @patch("backend.services.agent_command_service.AgentPresenceService.get_server", return_value=None)
    @patch("backend.services.agent_command_service.AgentPresenceService.redis_client", return_value=object())
    @patch("backend.services.agent_command_service.socketio")
    def test_call_server_falls_back_to_local_agent_when_redis_presence_missing(
        self,
        socketio,
        redis_client,
        get_server,
    ):
        socketio.call.return_value = {"success": True}
        socketio.emit = Mock()
        with patch(
            "backend.sockets.agent_socket.connected_agents",
            {
                "sid-one": {
                    "tenant_id": "tenant-paytel",
                    "server_id": "server-46",
                }
            },
        ):
            result = AgentCommandService.call_server(
                "sync_remote_app",
                {},
                tenant_id="tenant-paytel",
                server_id="server-46",
            )

        self.assertTrue(result["success"])
        socketio.call.assert_called_once_with(
            "sync_remote_app",
            {},
            namespace="/agent",
            to="sid-one",
            timeout=45,
        )
        socketio.emit.assert_not_called()

    @patch("backend.services.remote_app_service.PublishedApp.collection")
    def test_cleanup_status_does_not_replace_new_alias(self, collection):
        RemoteAppService.record_status(
            {"_id": "app-id"},
            "remove",
            {
                "success": True,
                "status": "unpublished",
                "alias": "old-alias",
                "remote_app_program": "||old-alias",
                "collection_name": "OldCollection",
            },
        )

        updates = collection.update_one.call_args.args[1]["$set"]
        self.assertEqual(updates["remote_app_publish_status"], "unpublished")
        self.assertNotIn("remote_app_alias", updates)
        self.assertNotIn("remote_app_program", updates)
        self.assertNotIn("rds_collection_name", updates)

    def test_managed_path_reuses_original_source_on_future_sync(self):
        spec = RemoteAppService._action_spec({
            "_id": "app-id",
            "remote_app_alias": "airtable-paytel",
            "remote_app_file_path": r"C:\Program Files\LR RemoteApps\airtable-paytel\Airtable.exe",
            "remote_app_source_file_path": r"C:\Users\Administrator\AppData\Local\Airtable\Airtable.exe",
            "remote_app_managed_file_path": r"C:\Program Files\LR RemoteApps\airtable-paytel\Airtable.exe",
        }, "publish")

        self.assertEqual(
            spec["payload"]["file_path"],
            r"C:\Users\Administrator\AppData\Local\Airtable\Airtable.exe",
        )

    @patch("backend.services.remote_app_service.PublishedApp.collection")
    def test_staged_result_persists_source_and_managed_paths(self, collection):
        RemoteAppService._record_result(
            {"_id": "app-id"},
            "publish",
            {
                "success": True,
                "status": "published",
                "file_path": r"C:\Program Files\LR RemoteApps\airtable-paytel\Airtable.exe",
                "source_file_path": r"C:\Users\Administrator\AppData\Local\Airtable\Airtable.exe",
                "managed_file_path": r"C:\Program Files\LR RemoteApps\airtable-paytel\Airtable.exe",
                "staged": True,
            },
            update_config=True,
        )

        updates = collection.update_one.call_args.args[1]["$set"]
        self.assertTrue(updates["remote_app_files_staged"])
        self.assertIn("Program Files", updates["remote_app_managed_file_path"])
        self.assertIn("Users", updates["remote_app_source_file_path"])

    @patch("backend.services.remote_app_service.PublishedApp.collection")
    def test_standalone_publish_clears_stale_broker_and_collection(self, collection):
        RemoteAppService._record_result(
            {"_id": "app-id"},
            "publish",
            {
                "success": True,
                "status": "published",
                "publication_mode": "standalone_registry",
                "connection_broker": "WIN-CLOUD87VM46",
            },
            update_config=True,
        )

        updates = collection.update_one.call_args.args[1]["$set"]
        self.assertEqual(updates["remote_app_publication_mode"], "standalone_registry")
        self.assertIsNone(updates["rds_collection_name"])
        self.assertIsNone(updates["rds_connection_broker"])

    @patch("backend.services.remote_app_service.Server.get_by_id")
    def test_action_spec_strips_connection_broker_for_local_host(self, get_server):
        import socket
        local_fqdn = socket.getfqdn()
        get_server.return_value = {
            "id": "server-id",
            "host": "127.0.0.1",
            "rds_connection_broker": local_fqdn,
        }
        app = {
            "_id": "app-id",
            "name": "Local App",
            "server_id": "server-id",
            "remote_app_alias": "local-app",
            "remote_app_file_path": r"C:\App\app.exe",
        }
        spec = RemoteAppService._action_spec(app, "publish")
        self.assertEqual(spec["payload"]["connection_broker"], "")

    @patch("backend.services.remote_app_service.PublishedApp.collection")
    def test_record_result_clears_local_host_broker(self, collection):
        import socket
        local_fqdn = socket.getfqdn()
        app = {"_id": "app-id", "name": "App"}
        RemoteAppService._record_result(
            app,
            "publish",
            {
                "success": True,
                "status": "published",
                "publication_mode": "rds_collection",
                "connection_broker": local_fqdn,
            },
            update_config=True,
        )
        updates = collection.update_one.call_args.args[1]["$set"]
        self.assertIsNone(updates["rds_connection_broker"])


class RemoteAppPowerShellRunnerTests(unittest.TestCase):
    def test_agent_script_stages_private_apps_with_read_execute_acl(self):
        self.assertIn("function Stage-LRRemoteApp", _REMOTE_APP_SCRIPT)
        self.assertIn("*S-1-5-32-545:(OI)(CI)RX", _REMOTE_APP_SCRIPT)
        self.assertIn("icacls.exe", _REMOTE_APP_SCRIPT)
        self.assertIn("function Set-LRStandaloneRemoteApp", _REMOTE_APP_SCRIPT)
        self.assertIn("TSAppAllowList", _REMOTE_APP_SCRIPT)
        self.assertIn("standalone_registry", _REMOTE_APP_SCRIPT)
        self.assertIn("function Test-LRIsLocalHost", _REMOTE_APP_SCRIPT)

    def test_three_thousand_apps_share_the_same_stateless_staging_contract(self):
        for index in range(3000):
            fields = RemoteAppService.normalize_app_fields({
                "name": f"Fleet App {index}",
                "remote_app_alias": f"fleet-app-{index}",
                "remote_app_file_path": rf"C:\Users\Administrator\Apps\Fleet{index}\app.exe",
            })
            self.assertEqual(fields["remote_app_program"], f"||fleet-app-{index}")
    @patch("shared.windows.remote_app.platform.system", return_value="Windows")
    @patch("shared.windows.remote_app.subprocess.run")
    def test_runner_decodes_agent_result(self, run, _system):
        run.return_value = Mock(
            returncode=0,
            stdout=json.dumps({
                "success": True,
                "status": "published",
                "alias": "calculator",
                "remote_app_program": "||calculator",
                "collection_name": "QuickSessionCollection",
            }) + "\n",
            stderr="",
        )

        result = run_remote_app_action({
            "action": "publish",
            "display_name": "Calculator",
            "alias": "calculator",
            "file_path": r"C:\Windows\System32\calc.exe",
        })

        self.assertTrue(result["success"])
        self.assertEqual(result["remote_app_program"], "||calculator")
        command = run.call_args.args[0]
        self.assertEqual(command[0], "powershell")
        self.assertIn("-File", command)


class ApplicationRemoteAppIntegrationTests(unittest.TestCase):
    @patch("backend.services.apps_service._app_response")
    @patch("backend.services.apps_service.RemoteAppService.sync_app")
    @patch("backend.services.apps_service.PublishedApp.get_by_id")
    @patch("backend.services.apps_service.PublishedApp.create")
    def test_create_saves_normalized_alias_and_starts_rds_sync(
        self,
        create,
        get_by_id,
        sync_app,
        app_response,
    ):
        created = {
            "_id": "app-id",
            "server_id": "server-id",
            "name": "Paint",
            "remote_app_alias": "mspaint",
            "remote_app_program": "||mspaint",
            "remote_app_file_path": r"C:\Windows\System32\mspaint.exe",
            "is_active": True,
        }
        create.return_value = created
        get_by_id.return_value = created
        sync_app.return_value = {
            "success": True,
            "status": "published",
            "alias": "mspaint",
        }
        app_response.return_value = {"id": "app-id"}

        result, status = ApplicationService.create_app(
            {
                "server_id": "server-id",
                "name": "Paint",
                "remote_app_alias": "mspaint",
                "remote_app_file_path": r"C:\Windows\System32\mspaint.exe",
            },
            user_id="admin-id",
            ip_address="127.0.0.1",
        )

        self.assertEqual(status, 201)
        saved = create.call_args.args[0]
        self.assertEqual(saved["remote_app_program"], "||mspaint")
        self.assertEqual(saved["remote_app_publish_status"], "pending")
        sync_app.assert_called_once_with(created)
        self.assertTrue(result["remote_app_sync"]["success"])


if __name__ == "__main__":
    unittest.main()
