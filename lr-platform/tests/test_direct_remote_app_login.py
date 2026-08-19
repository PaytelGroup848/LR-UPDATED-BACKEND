import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from bson import ObjectId
from flask import Flask
from flask_login import LoginManager

from backend.api.routers.auth_route import auth
from backend.api.routers.lr_route import lr_bp
from backend.models.user import MongoUser
from backend.services.lr_resources_service import LrResourcesService
from backend.services.portal_service import PortalService


class DirectRemoteAppLoginTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY='test-secret',
            SESSION_COOKIE_HTTPONLY=True,
            SESSION_COOKIE_SECURE=True,
            SESSION_COOKIE_SAMESITE='Lax',
            PORTAL_HOME_URL='/portal',
        )
        self.app.register_blueprint(auth)
        self.client = self.app.test_client()
        self.user = MongoUser({
            '_id': ObjectId(),
            'username': 'alice',
            'role': 'User',
            'is_active': True,
        })

    @patch('backend.api.routers.auth_route.AuthService.login')
    def test_remoteapp_login_returns_launcher_contract_without_selecting_an_app(
        self,
        login,
    ):
        login.return_value = self.user, 'Login successful', 200

        response = self.client.post('/login', json={
            'username': 'alice',
            'password': 'secret',
            'connection_type': 'remoteapp',
        })

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload['launch_transport'], 'rdp_remote_app_launcher')
        self.assertTrue(payload['launcher'])
        self.assertEqual(payload['resources_url'], '/api/lr/my-resources')
        self.assertEqual(payload['launch_endpoint'], '/api/lr/launch')
        self.assertNotIn('rdp_file_url', payload)
        self.assertNotIn('resource_id', payload)
        self.assertNotIn('launch_url', payload)
        self.assertNotIn('client_url', payload)
        self.assertEqual(payload['user']['username'], 'alice')
        cookie = response.headers.get('Set-Cookie', '')
        self.assertIn('HttpOnly', cookie)
        self.assertIn('Secure', cookie)
        self.assertIn('SameSite=Lax', cookie)
        login.assert_called_once_with('alice', 'secret', None, inactive_status=403, remember_me=False)

    @patch('backend.api.routers.auth_route.AuthService.login')
    def test_remoteapp_login_does_not_require_any_assigned_application(
        self,
        login,
    ):
        login.return_value = self.user, 'Login successful', 200

        response = self.client.post('/login', json={
            'username': 'alice',
            'password': 'secret',
            'connection_type': 'remoteapp',
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['launcher'])

    @patch('backend.api.routers.auth_route.AuthService.login')
    def test_remoteapp_invalid_credentials_use_error_contract(self, login):
        login.return_value = None, 'Invalid username or password', 401

        response = self.client.post('/login', json={
            'username': 'alice',
            'password': 'wrong',
            'connection_type': 'remoteapp',
        })

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {
            'success': False,
            'error': 'Invalid username or password',
        })

    @patch('backend.api.routers.auth_route.AuthService.login')
    def test_desktop_login_returns_native_rdp_launcher_contract(self, login):
        login.return_value = self.user, 'Login successful', 200

        response = self.client.post('/login', json={
            'username': 'alice',
            'password': 'secret',
            'connection_type': 'desktop',
        })

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['connection_type'], 'desktop')
        self.assertEqual(payload['launch_transport'], 'rdp_desktop_launcher')
        self.assertEqual(payload['launch_endpoint'], '/api/lr/desktop')
        self.assertTrue(payload['launcher'])
        self.assertEqual(payload['user']['username'], 'alice')
        self.assertNotIn('default_application_id', payload['user'])

    @patch('backend.api.routers.auth_route.LrResourcesService.launch_assigned_web_desktop')
    @patch('backend.api.routers.auth_route.AuthService.login')
    def test_legacy_login_without_mode_keeps_admin_portal_response(
        self,
        login,
        launch_web_desktop,
    ):
        login.return_value = self.user, 'Login successful', 200

        response = self.client.post('/login', json={
            'username': 'alice',
            'password': 'secret',
        })

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['redirect'], '/portal')
        self.assertEqual(payload['connection_type'], 'web')
        self.assertEqual(payload['user']['username'], 'alice')
        launch_web_desktop.assert_not_called()

    @patch('backend.api.routers.auth_route.LrResourcesService.launch_assigned_web_desktop')
    @patch('backend.api.routers.auth_route.UserLicenseService.block_response')
    @patch('backend.api.routers.auth_route.AuthService.login')
    def test_web_login_preserves_license_popup_contract(
        self,
        login,
        block_response,
        launch_web_desktop,
    ):
        login.return_value = self.user, 'Login successful', 200
        block_response.return_value = ({
            'success': False,
            'license_required': True,
            'message': 'Enter your LR-Key to continue.',
            'error': 'License key required',
            'license': {
                'status': 'TRIAL_ACTIVE',
                'blocked': True,
                'days_remaining': 7,
            },
        }, 402)

        response = self.client.post('/login', json={
            'username': 'alice',
            'password': 'secret',
            'connection_type': 'web',
        })

        payload = response.get_json()
        self.assertEqual(response.status_code, 403)
        self.assertFalse(payload['success'])
        self.assertTrue(payload['license_required'])
        self.assertEqual(payload['message'], 'Enter your LR-Key to continue.')
        self.assertEqual(payload['error'], 'License key required')
        self.assertTrue(payload['license']['blocked'])
        launch_web_desktop.assert_not_called()

    @patch('backend.api.routers.auth_route.LrResourcesService.launch_assigned_web_desktop')
    @patch('backend.api.routers.auth_route.UserLicenseService.block_response')
    @patch('backend.api.routers.auth_route.AuthService.login')
    def test_web_login_launches_direct_full_desktop(
        self,
        login,
        block_response,
        launch_web_desktop,
    ):
        login.return_value = self.user, 'Login successful', 200
        block_response.return_value = None
        launch_web_desktop.return_value = ({
            'success': True,
            'connection_type': 'web',
            'launch_transport': 'html5',
            'launch_url': 'http://guacamole/client',
            'session_id': 'session-id',
            'server_id': 'server-id',
            'server_name': 'Main Server',
        }, 200)

        response = self.client.post('/login', json={
            'username': 'alice',
            'password': 'secret',
            'connection_type': 'web',
        })

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['connection_type'], 'web')
        self.assertEqual(payload['launch_transport'], 'html5')
        self.assertEqual(payload['launch_url'], 'http://guacamole/client')
        self.assertNotIn('redirect', payload)
        self.assertNotIn('resource_id', payload)

    @patch('backend.services.lr_resources_service.PublishedApp.assigned_to_user')
    def test_single_assigned_remoteapp_is_selected(self, assigned_to_user):
        app = {'_id': ObjectId(), 'name': 'Calculator', 'remote_app_program': '||calculator'}
        assigned_to_user.return_value = [app]

        selected, error, status = LrResourcesService.select_login_remote_app(self.user)

        self.assertIs(selected, app)
        self.assertIsNone(error)
        self.assertEqual(status, 200)

    @patch('backend.services.lr_resources_service.ApplicationAssignment.defaults_for_user')
    @patch('backend.services.lr_resources_service.PublishedApp.assigned_to_user')
    def test_multiple_remoteapps_require_explicit_default(
        self,
        assigned_to_user,
        defaults_for_user,
    ):
        apps = [
            {'_id': ObjectId(), 'name': 'One', 'remote_app_program': '||one'},
            {'_id': ObjectId(), 'name': 'Two', 'remote_app_program': '||two'},
        ]
        assigned_to_user.return_value = apps
        defaults_for_user.return_value = []

        selected, error, status = LrResourcesService.select_login_remote_app(self.user)

        self.assertIsNone(selected)
        self.assertEqual(status, 409)
        self.assertIn('configure a default', error)

    @patch('backend.services.lr_resources_service.ApplicationAssignment.defaults_for_user')
    @patch('backend.services.lr_resources_service.PublishedApp.assigned_to_user')
    def test_multiple_remoteapps_select_explicit_assignment_default(
        self,
        assigned_to_user,
        defaults_for_user,
    ):
        first_id = ObjectId()
        default_id = ObjectId()
        apps = [
            {'_id': first_id, 'name': 'One', 'remote_app_program': '||one'},
            {'_id': default_id, 'name': 'Two', 'remote_app_program': '||two'},
        ]
        assigned_to_user.return_value = apps
        defaults_for_user.return_value = [{'app_id': default_id, 'is_default': True}]

        selected, error, status = LrResourcesService.select_login_remote_app(self.user)

        self.assertIs(selected, apps[1])
        self.assertIsNone(error)
        self.assertEqual(status, 200)

    @patch('backend.services.lr_resources_service.ApplicationAssignment.defaults_for_user')
    @patch('backend.services.lr_resources_service.PublishedApp.assigned_to_user')
    def test_only_configured_remoteapp_is_selected_from_mixed_assignments(
        self,
        assigned_to_user,
        defaults_for_user,
    ):
        assigned_to_user.return_value = [
            {'_id': ObjectId(), 'name': 'Configured', 'remote_app_program': '||one'},
            {'_id': ObjectId(), 'name': 'Missing configuration'},
        ]
        defaults_for_user.return_value = []

        selected, error, status = LrResourcesService.select_login_remote_app(self.user)

        self.assertEqual(selected['name'], 'Configured')
        self.assertIsNone(error)
        self.assertEqual(status, 200)

    @patch('backend.services.lr_resources_service.PortalService.launch_server')
    @patch('backend.services.lr_resources_service.Server.get_by_id')
    @patch('backend.services.lr_resources_service.PublishedApp.assigned_to_user')
    def test_web_desktop_launch_uses_unique_assigned_server_not_application(
        self,
        assigned_to_user,
        get_server,
        launch_server,
    ):
        server_id = ObjectId()
        assigned_to_user.return_value = [
            {'_id': ObjectId(), 'name': 'One', 'server_id': server_id},
            {'_id': ObjectId(), 'name': 'Two', 'server_id': server_id},
        ]
        get_server.return_value = {'_id': server_id, 'name': 'Main Server', 'is_active': True}
        launch_server.return_value = ({
            'success': True,
            'launch_url': 'http://guacamole/client',
            'session_id': 'session-id',
        }, 200)

        result, status = LrResourcesService.launch_assigned_web_desktop(
            self.user,
            '127.0.0.1',
            'test',
        )

        self.assertEqual(status, 200)
        self.assertEqual(result['launch_transport'], 'html5')
        self.assertNotIn('resource_id', result)
        launch_server.assert_called_once_with(
            data={'server_id': server_id, 'view_mode': 'html5'},
            user_id=self.user.id,
            ip_address='127.0.0.1',
            user_agent='test',
        )

    @patch('backend.services.portal_service.AccessPolicyService.can_launch_app')
    def test_inactive_assigned_server_returns_404(self, can_launch_app):
        can_launch_app.return_value = (
            False,
            'Assigned server is not available',
            {'_id': ObjectId(), 'name': 'Calculator'},
        )

        result, status = PortalService.launch_native_remote_app(
            app_id=ObjectId(),
            user_id=self.user.id,
            ip_address='127.0.0.1',
            user_agent='test',
        )

        self.assertEqual(status, 404)
        self.assertEqual(result, {
            'success': False,
            'error': 'Assigned server is not available',
        })

    @patch('backend.services.portal_service.PublishedApp.get_by_id')
    @patch('backend.services.portal_service.Server.get_by_id')
    @patch('backend.services.portal_service.RdpSession.collection')
    def test_native_rdp_file_is_owned_short_lived_and_single_use(
        self,
        session_collection,
        get_server,
        get_app,
    ):
        session_id = ObjectId()
        app_id = ObjectId()
        user_id = ObjectId()
        session_collection.find_one.return_value = {
            '_id': session_id,
            'user_id': user_id,
            'server_id': ObjectId(),
            'published_app_id': app_id,
            'native_remote_app': True,
            'rdp_file_expires_at': datetime.utcnow() + timedelta(minutes=1),
            'rdp_file_downloaded_at': None,
            'windows_username': 'alice',
        }
        session_collection.update_one.return_value.matched_count = 1
        get_server.return_value = {'host': '10.0.0.10', 'port': 3389, 'is_active': True}
        get_app.return_value = {
            '_id': app_id,
            'name': 'Calculator',
            'remote_app_program': '||calculator',
        }

        result, error, status = PortalService.get_rdp_file(
            str(session_id),
            str(user_id),
            require_native=True,
            consume_native=True,
        )

        self.assertEqual(status, 200)
        self.assertIsNone(error)
        self.assertIn('remoteapplicationmode:i:1', result['content'])
        self.assertNotIn('password', result['content'].lower())
        session_collection.update_one.assert_called_once()


class NativeRemoteAppFileEndpointTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='test-secret')
        login_manager = LoginManager(self.app)
        self.user = MongoUser({
            '_id': ObjectId(),
            'username': 'alice',
            'role': 'User',
            'is_active': True,
        })

        @login_manager.user_loader
        def load_user(_user_id):
            return self.user

        @login_manager.unauthorized_handler
        def unauthorized():
            return {'success': False, 'error': 'Authentication required'}, 401

        self.app.register_blueprint(lr_bp)
        self.client = self.app.test_client()
        with self.client.session_transaction() as browser_session:
            browser_session['_user_id'] = str(self.user.id)
            browser_session['_fresh'] = True

    @patch('backend.api.routers.lr_route.PortalService.get_rdp_file')
    @patch('backend.api.routers.lr_route.UserLicenseService.block_response')
    def test_file_endpoint_returns_native_rdp_headers(
        self,
        block_response,
        get_rdp_file,
    ):
        block_response.return_value = None
        get_rdp_file.return_value = ({
            'content': 'remoteapplicationmode:i:1\r\n',
            'filename': 'Calculator.rdp',
        }, None, 200)

        response = self.client.get('/api/lr/sessions/session-id/file.rdp')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'application/x-rdp')
        self.assertEqual(
            response.headers['Content-Disposition'],
            'attachment; filename="Calculator.rdp"',
        )
        self.assertEqual(response.headers['Cache-Control'], 'no-store, private')
        get_rdp_file.assert_called_once_with(
            session_id='session-id',
            user_id=self.user.id,
            require_native=True,
            consume_native=True,
        )


if __name__ == '__main__':
    unittest.main()
