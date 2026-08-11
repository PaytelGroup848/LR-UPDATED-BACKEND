import unittest
from unittest.mock import Mock, patch

from bson import ObjectId

from backend.models.user import MongoUser, User
from backend.services.access_policy_service import AccessPolicyService
from backend.services.auth_service import AuthService
from backend.services.lr_resources_service import LrResourcesService
from backend.services.windows_account_service import WindowsAccountService
from backend.sockets import agent_socket


class TenantWindowsUserCreationTests(unittest.TestCase):
    @patch.object(User, "collection")
    def test_same_username_can_be_created_in_different_tenants(self, collection):
        tenant_a = ObjectId()
        tenant_b = ObjectId()
        collection.find_one.return_value = None
        collection.insert_one.side_effect = [
            Mock(inserted_id=ObjectId()),
            Mock(inserted_id=ObjectId()),
        ]

        first = User.create("user1", "hashed", tenant_id=tenant_a)
        second = User.create("user1", "hashed", tenant_id=tenant_b)

        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(collection.find_one.call_args_list[0].args[0], {
            "username": "user1",
            "tenant_id": tenant_a,
        })
        self.assertEqual(collection.find_one.call_args_list[1].args[0], {
            "username": "user1",
            "tenant_id": tenant_b,
        })

    @patch("backend.services.auth_service.User.get_by_id")
    @patch("backend.services.auth_service.User.username_exists", return_value=False)
    @patch("backend.services.auth_service.WindowsAccountService.build_updates")
    def test_missing_server_fails_before_windows_or_database_create(
        self,
        build_updates,
        _username_exists,
        get_user,
    ):
        get_user.return_value = MongoUser({
            "_id": ObjectId(),
            "tenant_id": ObjectId(),
            "role": "Admin",
            "is_active": True,
        })

        result, status = AuthService.create_user({
            "username": "alice",
            "password": "Secret123!",
            "windows_account_enabled": True,
        }, actor_id=str(ObjectId()), ip_address="127.0.0.1")

        self.assertEqual(status, 400)
        self.assertIn("Select the Windows server", result["message"])
        build_updates.assert_not_called()

    @patch("backend.services.auth_service.User.get_by_id")
    @patch("backend.services.auth_service.User.update")
    @patch("backend.services.auth_service.User.create")
    @patch("backend.services.auth_service.User.username_exists", return_value=False)
    @patch("backend.services.auth_service.WindowsAccountService.build_updates")
    @patch("backend.services.auth_service.Server.get_by_id")
    def test_success_persists_exact_tenant_server_and_agent(
        self,
        get_server,
        build_updates,
        _username_exists,
        create_user,
        update_user,
        get_user,
    ):
        tenant_id = ObjectId()
        server_id = ObjectId()
        user_id = ObjectId()
        actor = MongoUser({
            "_id": ObjectId(),
            "tenant_id": tenant_id,
            "role": "Admin",
            "is_active": True,
        })
        created = MongoUser({
            "_id": user_id,
            "tenant_id": tenant_id,
            "username": "alice",
            "role": "User",
            "is_active": True,
        })
        saved = MongoUser({
            **created,
            "windows_username": "alice",
            "windows_password": "encrypted",
            "windows_account_enabled": True,
            "windows_account_provisioned": True,
            "windows_server_id": server_id,
            "windows_agent_id": "agent-b",
        })
        get_user.side_effect = [actor, saved]
        get_server.return_value = {
            "_id": server_id,
            "tenant_id": tenant_id,
            "name": "Company B Server",
            "host": "10.0.0.20",
            "port": 3389,
            "agent_id": "agent-b",
            "is_active": True,
        }
        build_updates.return_value = ({
            "windows_username": "alice",
            "windows_password": "encrypted",
            "windows_account_enabled": True,
            "windows_account_provisioned": True,
        }, None)
        create_user.return_value = created

        result, status = AuthService.create_user({
            "username": "alice",
            "password": "Secret123!",
            "windows_server_id": str(server_id),
            "windows_account_enabled": True,
            "windows_create_account": True,
        }, actor_id=str(actor.get("_id")), ip_address="127.0.0.1")

        self.assertEqual(status, 201)
        self.assertEqual(result["user"]["windows_server_id"], str(server_id))
        self.assertEqual(result["server"]["id"], str(server_id))
        get_server.assert_called_once_with(str(server_id), tenant_id)
        provisioning = build_updates.call_args.args[0]
        self.assertEqual(provisioning["_tenant_id"], tenant_id)
        self.assertEqual(provisioning["windows_server_id"], server_id)
        self.assertEqual(provisioning["windows_agent_id"], "agent-b")
        saved_updates = update_user.call_args.args[1]
        self.assertEqual(saved_updates["windows_server_id"], server_id)
        self.assertEqual(saved_updates["windows_agent_id"], "agent-b")


class TenantWindowsRoutingTests(unittest.TestCase):
    @patch("backend.services.lr_resources_service.PortalService.launch_native_desktop")
    @patch("backend.services.lr_resources_service.PublishedApp.assigned_to_user")
    @patch("backend.services.lr_resources_service.Server.get_by_id")
    def test_native_desktop_uses_persisted_windows_server_without_app_assignment(
        self,
        get_server,
        assigned_apps,
        launch_desktop,
    ):
        tenant_id = ObjectId()
        server_id = ObjectId()
        user_id = ObjectId()
        server = {
            "_id": server_id,
            "tenant_id": tenant_id,
            "name": "Company A Server",
            "is_active": True,
        }
        get_server.return_value = server
        launch_desktop.return_value = ({
            "success": True,
            "session_id": "session-id",
            "rdp_file_url": "/session.rdp",
        }, 200)

        result, status = LrResourcesService.launch_assigned_native_desktop(
            user={
                "_id": user_id,
                "tenant_id": tenant_id,
                "windows_server_id": server_id,
            },
            ip_address="127.0.0.1",
            user_agent="test",
        )

        self.assertEqual(status, 200)
        self.assertEqual(result["server_id"], str(server_id))
        get_server.assert_called_once_with(str(server_id), tenant_id)
        assigned_apps.assert_not_called()
        launch_desktop.assert_called_once_with(
            server_id=server_id,
            user_id=str(user_id),
            ip_address="127.0.0.1",
            user_agent="test",
        )

    @patch("backend.services.access_policy_service.Server.get_by_id")
    def test_user_cannot_launch_another_company_server_mapping(self, get_server):
        assigned_server_id = ObjectId()
        other_server_id = ObjectId()
        tenant_id = ObjectId()
        get_server.return_value = {
            "_id": other_server_id,
            "tenant_id": tenant_id,
            "is_active": True,
        }

        allowed, reason, _server = AccessPolicyService.can_launch_server({
            "tenant_id": tenant_id,
            "role": "User",
            "windows_server_id": assigned_server_id,
        }, other_server_id)

        self.assertFalse(allowed)
        self.assertEqual(reason, "This server is not assigned to the user")


class CompanyAwareLoginTests(unittest.TestCase):
    @patch("backend.services.auth_service.User.find_all_by_username")
    def test_duplicate_username_requires_company_code(self, find_users):
        find_users.return_value = [Mock(), Mock()]

        user, message, status = AuthService.login("user1", "secret")

        self.assertIsNone(user)
        self.assertEqual(status, 400)
        self.assertEqual(message, "Company code is required for this username")

    @patch("backend.services.auth_service.User.update_login")
    @patch("backend.services.auth_service.login_user")
    @patch("backend.services.auth_service._password_matches", return_value=True)
    @patch("backend.services.auth_service.User.find_by_username")
    @patch("backend.services.auth_service.Tenant.get_by_code")
    def test_company_code_resolves_same_local_username_inside_tenant(
        self,
        get_tenant,
        find_user,
        _password_matches,
        _login_user,
        update_login,
    ):
        tenant_id = ObjectId()
        tenant = {
            "_id": tenant_id,
            "company_slug": "company-a",
            "is_active": True,
            "registration_status": "active",
        }
        user = MongoUser({
            "_id": ObjectId(),
            "tenant_id": tenant_id,
            "username": "user1",
            "password": "hashed",
            "role": "User",
            "is_active": True,
            "windows_username": "user1",
            "windows_password": "encrypted",
        })
        get_tenant.return_value = tenant
        find_user.return_value = user

        logged_in, message, status = AuthService.login(
            "user1",
            "secret",
            company="company-a",
        )

        self.assertIs(logged_in, user)
        self.assertEqual(status, 200)
        self.assertEqual(message, "Login successful")
        find_user.assert_called_once_with("user1", tenant_id)
        update_login.assert_called_once_with(user.id, tenant_id=tenant_id)


class ExactAgentTargetTests(unittest.TestCase):
    def setUp(self):
        agent_socket.connected_agents.clear()

    def tearDown(self):
        agent_socket.connected_agents.clear()

    @patch("backend.services.windows_account_service.socketio.call")
    def test_windows_account_is_sent_only_to_selected_tenant_server(self, call):
        agent_socket.connected_agents.update({
            "sid-a": {
                "tenant_id": "tenant-a",
                "server_id": "server-a",
                "os": "Windows Server",
            },
            "sid-b": {
                "tenant_id": "tenant-b",
                "server_id": "server-b",
                "os": "Windows Server",
            },
        })
        call.return_value = {"success": True, "message": "Windows account created"}

        result = WindowsAccountService.create_via_agent(
            "user1",
            "Secret123!",
            tenant_id="tenant-b",
            server_id="server-b",
        )

        self.assertTrue(result["success"])
        self.assertEqual(call.call_args.kwargs["to"], "sid-b")


if __name__ == "__main__":
    unittest.main()
