import unittest
from unittest.mock import Mock, patch

from bson import ObjectId
from flask import Flask
from flask_login import LoginManager

from backend.api.routers.lr_route import lr_bp
from backend.models.user import MongoUser
from backend.services.lr_resources_service import LrResourcesService
from backend.services.portal_service import PortalService


class NativeDesktopTests(unittest.TestCase):
    @patch("backend.services.lr_resources_service.PortalService.launch_native_desktop")
    @patch("backend.services.lr_resources_service.Server.get_by_id")
    @patch("backend.services.lr_resources_service.PublishedApp.assigned_to_user")
    def test_assigned_server_launches_full_native_desktop(
        self,
        assigned_to_user,
        get_server,
        launch_native_desktop,
    ):
        server_id = ObjectId()
        user_id = ObjectId()
        user = {"_id": user_id, "username": "alice"}
        assigned_to_user.return_value = [
            {"_id": ObjectId(), "server_id": server_id, "name": "Calculator"},
        ]
        get_server.return_value = {
            "_id": server_id,
            "name": "Main Lr Remote Access Server",
            "is_active": True,
        }
        launch_native_desktop.return_value = ({
            "success": True,
            "session_id": "session-id",
            "rdp_file_url": "/portal/api/sessions/session-id/rdp-file",
        }, 200)

        result, status = LrResourcesService.launch_assigned_native_desktop(
            user=user,
            ip_address="127.0.0.1",
            user_agent="test",
        )

        self.assertEqual(status, 200)
        self.assertEqual(result["connection_type"], "desktop")
        self.assertEqual(result["launch_transport"], "rdp_desktop")
        self.assertEqual(result["server_name"], "Main Lr Remote Access Server")
        launch_native_desktop.assert_called_once_with(
            server_id=server_id,
            user_id=str(user_id),
            ip_address="127.0.0.1",
            user_agent="test",
        )

    @patch("backend.services.lr_resources_service.PublishedApp.assigned_to_user")
    def test_desktop_requires_an_assigned_server(self, assigned_to_user):
        assigned_to_user.return_value = []

        result, status = LrResourcesService.launch_assigned_native_desktop(
            user={"_id": ObjectId(), "username": "alice"},
            ip_address="127.0.0.1",
            user_agent="test",
        )

        self.assertEqual(status, 403)
        self.assertEqual(result["error"], "No server access is assigned to this user")

    @patch("backend.services.portal_service.PortalService._create_launch_session")
    @patch("backend.services.portal_service._native_rdp_precheck")
    @patch("backend.services.portal_service.AccessPolicyService.can_launch_server")
    @patch("backend.services.portal_service.User.get_by_id")
    def test_native_desktop_reuses_existing_rdp_session_generator(
        self,
        get_user,
        can_launch_server,
        precheck,
        create_launch_session,
    ):
        user = {"_id": "user-id", "username": "alice"}
        server = {
            "_id": "server-id",
            "name": "Main Server",
            "host": "10.0.0.10",
            "port": 3389,
            "is_active": True,
        }
        get_user.return_value = user
        can_launch_server.return_value = True, None, server
        precheck.return_value = None
        create_launch_session.return_value = ({"success": True}, 200)

        result = PortalService.launch_native_desktop(
            server_id="server-id",
            user_id="user-id",
            ip_address="127.0.0.1",
            user_agent="test",
        )

        self.assertEqual(result, ({"success": True}, 200))
        precheck.assert_called_once_with("10.0.0.10", 3389)
        create_launch_session.assert_called_once_with(
            user_id="user-id",
            server=server,
            app=None,
            ip_address="127.0.0.1",
            user_agent="test",
            requested_view="full_desktop",
            force_html5_gateway=False,
            ignore_stored_display_mode=True,
        )

    @patch("backend.services.portal_service.Server.get_by_id")
    @patch("backend.services.portal_service.RdpSession.collection")
    def test_generated_desktop_rdp_has_no_remoteapp_program(
        self,
        session_collection,
        get_server,
    ):
        session_id = ObjectId()
        user_id = ObjectId()
        session_collection.find_one.return_value = {
            "_id": session_id,
            "user_id": user_id,
            "server_id": ObjectId(),
            "native_remote_app": False,
            "windows_username": "alice",
            "windows_domain": "LAB",
            "display_mode": "full_desktop",
        }
        get_server.return_value = {
            "name": "Main Server",
            "host": "10.0.0.10",
            "port": 3389,
            "is_active": True,
        }

        result, error, status = PortalService.get_rdp_file(
            session_id=str(session_id),
            user_id=str(user_id),
            consume_native=False,
        )

        self.assertEqual(status, 200)
        self.assertIsNone(error)
        self.assertIn("screen mode id:i:2", result["content"])
        self.assertIn("full address:s:10.0.0.10", result["content"])
        self.assertNotIn("remoteapplicationmode", result["content"])
        self.assertNotIn("remoteapplicationprogram", result["content"])


class NativeDesktopEndpointTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        login_manager = LoginManager(self.app)
        self.user = MongoUser({
            "_id": ObjectId(),
            "username": "alice",
            "role": "User",
            "is_active": True,
        })

        @login_manager.user_loader
        def load_user(_user_id):
            return self.user

        self.app.register_blueprint(lr_bp)
        self.client = self.app.test_client()
        with self.client.session_transaction() as browser_session:
            browser_session["_user_id"] = self.user.id
            browser_session["_fresh"] = True

    @patch("backend.api.routers.lr_route.LrResourcesService.launch_assigned_native_desktop")
    @patch("backend.api.routers.lr_route.UserLicenseService.block_response")
    def test_endpoint_is_license_gated_then_launches_assigned_desktop(
        self,
        block_response,
        launch_desktop,
    ):
        block_response.return_value = None
        launch_desktop.return_value = ({
            "success": True,
            "rdp_file_url": "/portal/api/sessions/session-id/rdp-file",
        }, 200)

        response = self.client.post("/api/lr/desktop", json={})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json()["rdp_file_url"],
            "/portal/api/sessions/session-id/rdp-file",
        )
        block_response.assert_called_once()
        launch_desktop.assert_called_once()

    @patch("backend.api.routers.lr_route.LrResourcesService.launch_assigned_native_desktop")
    @patch("backend.api.routers.lr_route.UserLicenseService.block_response")
    def test_expired_trial_blocks_desktop_before_session_creation(
        self,
        block_response,
        launch_desktop,
    ):
        block_response.return_value = ({
            "success": False,
            "license_required": True,
            "error": "License key required",
        }, 402)

        response = self.client.post("/api/lr/desktop", json={})

        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.get_json()["license_required"])
        launch_desktop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
