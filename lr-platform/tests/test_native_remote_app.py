import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from bson import ObjectId
from flask import Flask

from backend.models.rdp_session import RdpSession
from backend.manager.session_manager import SessionManager
from backend.services.lr_resources_service import LrResourcesService
from backend.services.portal_service import PortalService, _native_remote_app_rdp_lines
from backend.services.sessions_service import SessionsService


class NativeRemoteAppTests(unittest.TestCase):
    @patch('backend.services.lr_resources_service.PublishedApp.assigned_to_user')
    def test_my_resources_returns_published_folders_separately(self, assigned_to_user):
        assigned_to_user.return_value = [
            {'_id': 'app-id', 'name': 'Calculator', 'remote_app_program': '||calculator'},
            {
                '_id': 'folder-id',
                'name': 'Nikhil (Read)',
                'item_type': 'folder',
                'folder_path': r'C:\Data\Nikhil',
                'remote_app_program': '||nikhil-read',
                'remote_app_publish_status': 'published',
            },
        ]

        result, status_code = LrResourcesService.my_resources('user-id')

        self.assertEqual(status_code, 200)
        self.assertEqual([item['id'] for item in result['applications']], ['app-id'])
        self.assertEqual([item['id'] for item in result['folders']], ['folder-id'])

    @patch('backend.services.lr_resources_service.PortalService.launch_remote_app')
    @patch('backend.services.lr_resources_service.User.get_by_id')
    @patch('backend.services.lr_resources_service.PublishedApp.get_by_id')
    def test_folder_resource_uses_browser_remote_app_launch(self, get_by_id, get_user, launch_remote_app):
        get_user.return_value = {'_id': 'user-id', 'tenant_id': 'tenant-id'}
        get_by_id.return_value = {
            '_id': 'folder-id',
            'name': 'Nikhil (Read)',
            'item_type': 'folder',
            'folder_path': r'C:\Data\Nikhil',
            'remote_app_program': '||nikhil-read',
            'remote_app_publish_status': 'published',
        }
        launch_remote_app.return_value = ({'success': True}, 200)

        result = LrResourcesService.launch_resource(
            data={
                'resource_id': 'folder-id',
                'type': 'folder',
                'connection_type': 'remoteapp',
            },
            user_id='user-id',
            ip_address='127.0.0.1',
            user_agent='test',
        )

        self.assertEqual(result, ({'success': True}, 200))
        launch_remote_app.assert_called_once()

    @patch('backend.services.lr_resources_service.PortalService.launch_remote_app')
    @patch('backend.services.lr_resources_service.User.get_by_id')
    @patch('backend.services.lr_resources_service.PublishedApp.get_by_id')
    def test_frontend_remote_app_api_uses_browser_remote_app_launch(
        self,
        get_by_id,
        get_user,
        launch_remote_app,
    ):
        get_user.return_value = {'_id': 'user-id', 'tenant_id': 'tenant-id'}
        get_by_id.return_value = {
            '_id': 'app-id',
            'name': 'Calculator',
            'remote_app_program': '||calculator',
        }
        launch_remote_app.return_value = ({'success': True}, 200)

        result = LrResourcesService.launch_resource(
            data={
                'resource_id': 'app-id',
                'type': 'application',
                'connection_type': 'remoteapp',
            },
            user_id='user-id',
            ip_address='127.0.0.1',
            user_agent='test',
        )

        self.assertEqual(result, ({'success': True}, 200))
        get_by_id.assert_called_once_with('app-id', 'tenant-id')
        launch_remote_app.assert_called_once_with(
            app_id='app-id',
            user_id='user-id',
            ip_address='127.0.0.1',
            user_agent='test',
        )

    @patch('backend.services.lr_resources_service.PortalService.launch_remote_app')
    @patch('backend.services.lr_resources_service.User.get_by_id')
    @patch('backend.services.lr_resources_service.PublishedApp.get_by_id')
    def test_launch_resource_uses_current_user_tenant_for_app_lookup(
        self,
        get_by_id,
        get_user,
        launch_remote_app,
    ):
        tenant_id = ObjectId()
        user_id = ObjectId()
        get_user.return_value = {
            '_id': user_id,
            'tenant_id': tenant_id,
        }
        get_by_id.return_value = {
            '_id': 'app-id',
            'name': 'Calculator',
            'remote_app_program': '||calculator',
        }
        launch_remote_app.return_value = ({'success': True}, 200)

        result = LrResourcesService.launch_resource(
            data={
                'resource_id': 'app-id',
                'type': 'application',
                'connection_type': 'remoteapp',
            },
            user_id=str(user_id),
            ip_address='127.0.0.1',
            user_agent='test',
        )

        self.assertEqual(result, ({'success': True}, 200))
        get_by_id.assert_called_once_with('app-id', tenant_id)
        get_user.assert_called_once_with(str(user_id))
        launch_remote_app.assert_called_once()

    @patch('backend.models.rdp_session.RdpSession.collection.insert_one')
    def test_session_model_persists_native_remote_app_marker(self, insert_one):
        tenant_id = ObjectId()
        user_id = ObjectId()
        get_user.return_value = {
            '_id': user_id,
            'tenant_id': tenant_id,
        }
        get_by_id.return_value = {
            '_id': 'app-id',
            'name': 'Calculator',
            'remote_app_program': '||calculator',
        }
        launch_remote_app.return_value = ({'success': True}, 200)

        result = LrResourcesService.launch_resource(
            data={
                'resource_id': 'app-id',
                'type': 'application',
                'connection_type': 'remoteapp',
            },
            user_id=str(user_id),
            ip_address='127.0.0.1',
            user_agent='test',
        )

        self.assertEqual(result, ({'success': True}, 200))
        get_by_id.assert_called_once_with('app-id', tenant_id)
        get_user.assert_called_once_with(str(user_id))
        launch_remote_app.assert_called_once()

    @patch('backend.models.rdp_session.RdpSession.collection.insert_one')
    def test_session_model_persists_native_remote_app_marker(self, insert_one):
        insert_one.return_value.inserted_id = 'session-id'

        session = RdpSession.create({'native_remote_app': True})

        self.assertTrue(session['native_remote_app'])
        persisted_session = insert_one.call_args.args[0]
        self.assertTrue(persisted_session['native_remote_app'])

    def test_non_native_session_payload_keeps_existing_shape(self):
        payload = RdpSession.to_dict({
            '_id': 'session-id',
            'native_remote_app': False,
            'guac_token': 'internal-admin-token',
            'launch_url': 'http://guacamole/client?token=internal-admin-token',
        })

        self.assertNotIn('native_remote_app', payload)
        self.assertNotIn('rdp_file_expires_at', payload)
        self.assertNotIn('rdp_file_downloaded_at', payload)
        self.assertNotIn('guac_token', payload)
        self.assertNotIn('launch_url', payload)

    @patch('backend.services.portal_service.RdpSession.collection')
    @patch('backend.services.portal_service.User.get_by_id')
    @patch('backend.services.portal_service.PortalService._create_launch_session')
    @patch('backend.services.portal_service.Server.get_by_id')
    @patch('backend.services.portal_service.AccessPolicyService.can_launch_app')
    def test_browser_launch_returns_html5_remoteapp_and_native_compatibility(
        self,
        can_launch_app,
        get_server,
        create_launch_session,
        get_user,
        session_collection,
    ):
        app_id = ObjectId()
        server_id = ObjectId()
        session_id = ObjectId()
        tenant_id = ObjectId()
        app = {
            '_id': app_id,
            'server_id': server_id,
            'name': 'Calculator',
            'remote_app_program': '||calculator',
        }
        server = {'_id': server_id, 'is_active': True, 'host': '10.0.0.10', 'port': 3389}
        user = {'_id': ObjectId(), 'tenant_id': tenant_id}
        can_launch_app.return_value = True, None, app
        get_server.return_value = server
        get_user.return_value = user
        create_launch_session.return_value = ({
            'success': True,
            'session_id': str(session_id),
            'connection_id': 'guac-connection-id',
            'launch_url': 'http://guacamole/client?token=internal-admin-token',
            'session': {},
        }, 200)
        session_collection.update_one.return_value.matched_count = 1

        flask_app = Flask(__name__)
        flask_app.config.update(SECRET_KEY='test-secret')
        with flask_app.test_request_context('/', base_url='https://lr.example'):
            result, status_code = PortalService.launch_remote_app(
                app_id=app_id,
                user_id=user['_id'],
                ip_address='127.0.0.1',
                user_agent='test',
            )

        self.assertEqual(status_code, 200)
        self.assertEqual(result['launch_transport'], 'html5_remoteapp')
        self.assertEqual(result['application_name'], 'Calculator')
        self.assertEqual(result['resource_id'], str(app_id))
        self.assertIn(f'/api/lr/sessions/{session_id}/open?ticket=', result['launch_url'])
        self.assertNotIn('internal-admin-token', result['launch_url'])
        self.assertEqual(result['rdp_file_url'], f'/api/lr/sessions/{session_id}/file.rdp')
        self.assertNotIn('password', repr(result).lower())
        create_launch_session.assert_called_once_with(
            user_id=user['_id'],
            server=server,
            app=app,
            ip_address='127.0.0.1',
            user_agent='test',
            requested_view='remote_app',
            force_html5_gateway=True,
            ignore_stored_display_mode=True,
            require_remote_app=True,
        )
        stored_fields = session_collection.update_one.call_args.args[1]['$set']
        self.assertTrue(stored_fields['native_remote_app'])
        self.assertTrue(stored_fields['browser_launch_nonce_hash'])

    @patch('backend.services.portal_service.RdpSession.collection')
    @patch('backend.services.portal_service.AccessPolicyService.can_view_session')
    def test_browser_launch_ticket_is_user_bound_and_single_use(
        self,
        can_view_session,
        session_collection,
    ):
        from backend.services.portal_service import _browser_launch_ticket

        session_id = ObjectId()
        user_id = ObjectId()
        tenant_id = ObjectId()
        app_id = ObjectId()
        server_id = ObjectId()
        user = {'_id': user_id, 'tenant_id': tenant_id}
        session = {
            '_id': session_id,
            'user_id': user_id,
            'tenant_id': tenant_id,
            'published_app_id': app_id,
            'server_id': server_id,
            'status': 'active',
            'launch_url': 'http://guacamole/client?token=internal-admin-token',
            'browser_launch_expires_at': datetime.utcnow() + timedelta(minutes=1),
        }
        flask_app = Flask(__name__)
        flask_app.config.update(SECRET_KEY='test-secret')
        with flask_app.app_context():
            ticket, nonce_hash = _browser_launch_ticket(
                session,
                user,
                {'_id': app_id},
                {'_id': server_id},
            )
            session['browser_launch_nonce_hash'] = nonce_hash
            can_view_session.return_value = True, None, session
            first_update = Mock(matched_count=1)
            second_update = Mock(matched_count=0)
            session_collection.update_one.side_effect = [first_update, second_update]

            first, first_status = PortalService.consume_browser_remote_app_launch(
                str(session_id), ticket, user,
            )
            second, second_status = PortalService.consume_browser_remote_app_launch(
                str(session_id), ticket, user,
            )

        self.assertEqual(first_status, 200)
        self.assertEqual(first['redirect_url'], session['launch_url'])
        self.assertEqual(second_status, 409)
        self.assertIn('already been used', second['error'])

    @patch('backend.manager.guacamole_manager.get_guac_client')
    @patch('backend.services.sessions_service.RdpSession.collection')
    def test_logout_cleanup_closes_session_and_deletes_guacamole_connection(
        self,
        session_collection,
        get_guac_client,
    ):
        session_id = ObjectId()
        session_collection.find.return_value = [{
            '_id': session_id,
            'guac_connection_id': 'guac-connection-id',
            'status': 'active',
        }]
        get_guac_client.return_value.delete_connection.return_value = {'success': True}

        result = SessionsService.close_user_sessions('user-id', reason='logout')

        self.assertTrue(result['success'])
        self.assertEqual(result['closed'], 1)
        get_guac_client.return_value.delete_connection.assert_called_once_with('guac-connection-id')
        update = session_collection.update_one.call_args.args[1]
        self.assertEqual(update['$set']['status'], 'closed')
        self.assertEqual(update['$set']['close_reason'], 'logout')
        self.assertIn('launch_url', update['$unset'])
        self.assertIn('guac_token', update['$unset'])

    @patch('backend.services.sessions_service.SessionsService._cleanup_guacamole_connection')
    @patch('backend.manager.session_manager.RdpSession.collection')
    def test_expired_session_cleanup_deletes_gateway_connection(
        self,
        session_collection,
        cleanup_connection,
    ):
        session_collection.find.return_value = [{
            '_id': ObjectId(),
            'guac_connection_id': 'guac-connection-id',
            'status': 'active',
        }]
        session_collection.update_one.return_value.modified_count = 1

        count = SessionManager().cleanup_stale_sessions()

        self.assertEqual(count, 1)
        cleanup_connection.assert_called_once()
        update = session_collection.update_one.call_args.args[1]
        self.assertEqual(update['$set']['close_reason'], 'expired')
        self.assertIn('browser_launch_nonce_hash', update['$unset'])

    def test_rdp_lines_enable_remote_app_for_alias_or_executable(self):
        lines = _native_remote_app_rdp_lines({
            'name': 'Calculator',
            'remote_app_program': '||calculator',
            'working_directory': r'C:\Windows\System32',
            'arguments': '/example',
        })

        self.assertIn('remoteapplicationmode:i:1', lines)
        self.assertIn('remoteapplicationprogram:s:||calculator', lines)
        self.assertIn('remoteapplicationname:s:Calculator', lines)
        self.assertIn('remoteapplicationcmdline:s:/example', lines)
        self.assertIn(r'shell working directory:s:C:\Windows\System32', lines)

    def test_rdp_lines_normalize_remote_app_alias(self):
        lines = _native_remote_app_rdp_lines({
            'name': 'Airtable',
            'remote_app_program': '||Airtable',
            'remote_app_alias': 'Airtable',
        })

        self.assertIn('remoteapplicationprogram:s:||airtable', lines)

    def test_rdp_lines_accept_raw_alias_without_pipes(self):
        lines = _native_remote_app_rdp_lines({
            'name': 'Airtable',
            'remote_app_program': 'Airtable',
        })

        self.assertIn('remoteapplicationprogram:s:||airtable', lines)

    def test_rdp_lines_fallback_to_remote_app_alias_when_program_is_path(self):
        lines = _native_remote_app_rdp_lines({
            'name': 'Airtable',
            'remote_app_program': r'C:\Program Files\Airtable\Airtable.exe',
            'remote_app_alias': 'airtable-paytel',
        })

        self.assertIn('remoteapplicationprogram:s:||airtable-paytel', lines)

    @patch('backend.services.portal_service.PublishedApp.get_by_id')
    @patch('backend.services.portal_service.RdpSession.collection')
    @patch('backend.services.portal_service.Server.get_by_id')
    def test_get_rdp_file_uses_session_tenant_for_app_lookup(
        self,
        get_server,
        session_collection,
        get_app,
    ):
        session_id = ObjectId()
        user_id = ObjectId()
        tenant_id = ObjectId()
        published_app_id = ObjectId()

        session_collection.find_one.return_value = {
            '_id': session_id,
            'user_id': user_id,
            'server_id': ObjectId(),
            'published_app_id': published_app_id,
            'tenant_id': tenant_id,
            'native_remote_app': True,
            'rdp_file_expires_at': datetime.utcnow() + timedelta(minutes=1),
            'rdp_file_downloaded_at': None,
            'windows_username': 'alice',
        }
        session_collection.update_one.return_value.matched_count = 1
        get_server.return_value = {
            'host': '10.0.0.10',
            'port': 3389,
            'is_active': True,
        }
        get_app.return_value = {
            '_id': published_app_id,
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
        get_app.assert_called_once_with(published_app_id, tenant_id)

    @patch('backend.services.portal_service.PortalService._create_launch_session')
    @patch('backend.services.portal_service.Server.get_by_id')
    @patch('backend.services.portal_service.AccessPolicyService.can_launch_app')
    def test_native_launch_isolated_from_html5_and_desktop_modes(
        self,
        can_launch_app,
        get_server,
        create_launch_session,
    ):
        app = {
            '_id': 'app-id',
            'server_id': 'server-id',
            'name': 'Calculator',
            'remote_app_program': '||calculator',
        }
        server = {'_id': 'server-id', 'is_active': True, 'host': '10.0.0.10', 'port': 3389}
        can_launch_app.return_value = True, None, app
        get_server.return_value = server
        create_launch_session.return_value = ({'success': True}, 200)

        result = PortalService.launch_native_remote_app(
            app_id='app-id',
            user_id='user-id',
            ip_address='127.0.0.1',
            user_agent='test',
        )

        self.assertEqual(result, ({'success': True}, 200))
        create_launch_session.assert_called_once_with(
            user_id='user-id',
            server=server,
            app=app,
            ip_address='127.0.0.1',
            user_agent='test',
            requested_view='remote_app',
            force_html5_gateway=False,
            ignore_stored_display_mode=True,
            native_remote_app=True,
        )

    @patch('backend.services.portal_service.PortalService._create_launch_session')
    @patch('backend.services.portal_service.Server.get_by_id')
    @patch('backend.services.portal_service.AccessPolicyService.can_launch_app')
    def test_native_launch_allows_published_folder(
        self,
        can_launch_app,
        get_server,
        create_launch_session,
    ):
        app = {
            '_id': 'folder-id',
            'server_id': 'server-id',
            'name': 'Nikhil (Read)',
            'item_type': 'folder',
            'remote_app_program': '||nikhil-read',
            'arguments': r'C:\Data\Nikhil',
        }
        server = {'_id': 'server-id', 'is_active': True, 'host': '10.0.0.10', 'port': 3389}
        can_launch_app.return_value = True, None, app
        get_server.return_value = server
        create_launch_session.return_value = ({'success': True}, 200)

        result = PortalService.launch_native_remote_app(
            app_id='folder-id',
            user_id='user-id',
            ip_address='127.0.0.1',
            user_agent='test',
        )

        self.assertEqual(result, ({'success': True}, 200))
        create_launch_session.assert_called_once()

    @patch('backend.services.portal_service.AccessPolicyService.can_launch_app')
    def test_native_launch_never_falls_back_without_remote_app_program(self, can_launch_app):
        can_launch_app.return_value = True, None, {
            '_id': 'app-id',
            'server_id': 'server-id',
            'name': 'Missing program',
        }

        result, status_code = PortalService.launch_native_remote_app(
            app_id='app-id',
            user_id='user-id',
            ip_address='127.0.0.1',
            user_agent='test',
        )

        self.assertEqual(status_code, 400)
        self.assertEqual(result['error'], 'Published application is missing its RemoteApp program')


if __name__ == '__main__':
    unittest.main()
