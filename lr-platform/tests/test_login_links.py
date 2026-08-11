import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from bson import ObjectId
from flask import Flask
from flask_login import LoginManager

from backend.api.routers.auth_route import auth
from backend.api.routers.admin_features_route import admin_features
from backend.core.app_factory import register_cors
from backend.models.user import MongoUser
from backend.services.admin_features_service import AdminFeatureService


class LoginLinkEndpointTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            TESTING=True,
            SECRET_KEY='test-secret',
            FRONTEND_URL='http://frontend.example:3000',
        )
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

        self.app.register_blueprint(auth)
        self.app.register_blueprint(admin_features)
        register_cors(self.app)
        self.client = self.app.test_client()

    def test_generated_url_uses_authenticated_admin_company_code(self):
        tenant_id = ObjectId()
        actor = MongoUser({
            '_id': ObjectId(),
            'tenant_id': tenant_id,
            'username': 'admin',
            'role': 'Admin',
            'is_active': True,
        })
        link = {
            '_id': ObjectId(),
            'tenant_id': tenant_id,
            'token': 'generated-token',
            'user_id': self.user.get('_id'),
            'one_time': True,
        }
        with self.app.test_request_context('/api/generate-url'):
            with patch(
                'backend.services.admin_features_service.User.get_by_id',
                return_value=self.user,
            ), patch(
                'backend.services.admin_features_service.Tenant.get_by_id',
                return_value={
                    '_id': tenant_id,
                    'company_code': 'Acme_Corp',
                    'is_active': True,
                },
            ), patch(
                'backend.services.admin_features_service.token_urlsafe',
                return_value='generated-token',
            ), patch(
                'backend.services.admin_features_service.LoginLink.create',
                return_value=link,
            ) as create_link, patch(
                'backend.services.admin_features_service.LoginLink.to_dict',
                return_value={'id': str(link['_id'])},
            ):
                payload, status = AdminFeatureService.generate_url(
                    {
                        'user_id': self.user.id,
                        'expires_minutes': 60,
                        'one_time': True,
                        'company_code': 'another-company',
                    },
                    actor,
                    '127.0.0.1',
                )

        parsed = urlparse(payload['url'])
        self.assertEqual(status, 201)
        self.assertEqual(parsed.scheme, 'http')
        self.assertEqual(parsed.netloc, 'frontend.example:3000')
        self.assertEqual(parsed.path, '/login-link/generated-token')
        self.assertEqual(parse_qs(parsed.query), {'company_code': ['acme_corp']})
        self.assertEqual(payload['company_code'], 'acme_corp')
        self.assertEqual(create_link.call_args.kwargs['tenant_id'], tenant_id)

    def test_company_portal_url_opens_login_page_without_auto_login_token(self):
        tenant_id = ObjectId()
        actor = MongoUser({
            '_id': ObjectId(),
            'tenant_id': tenant_id,
            'username': 'admin',
            'role': 'Admin',
            'is_active': True,
        })
        with self.app.test_request_context('/api/generate-portal-url'):
            with patch(
                'backend.services.admin_features_service.Tenant.get_by_id',
                return_value={
                    '_id': tenant_id,
                    'company_code': 'Paytel',
                    'is_active': True,
                },
            ), patch(
                'backend.services.admin_features_service.AuditService.log'
            ):
                payload, status = AdminFeatureService.generate_portal_url(
                    actor,
                    '127.0.0.1',
                )

        parsed = urlparse(payload['url'])
        self.assertEqual(status, 200)
        self.assertEqual(parsed.path, '/login')
        self.assertEqual(parse_qs(parsed.query), {'company_code': ['paytel']})
        self.assertNotIn('login-link', payload['url'])
        self.assertNotIn('token', payload['url'])

    @patch('backend.api.routers.admin_features_route.AdminFeatureService.generate_portal_url')
    def test_non_admin_cannot_generate_company_portal_url(self, generate_portal_url):
        with self.client.session_transaction() as session:
            session['_user_id'] = self.user.id
            session['_fresh'] = True

        response = self.client.post('/api/generate-portal-url', json={})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()['code'], 'admin_required')
        generate_portal_url.assert_not_called()

    @patch('backend.api.routers.admin_features_route.AdminFeatureService.generate_url')
    def test_non_admin_cannot_generate_login_url(self, generate_url):
        with self.client.session_transaction() as session:
            session['_user_id'] = self.user.id
            session['_fresh'] = True

        response = self.client.post(
            '/api/generate-url',
            json={'user_id': self.user.id},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()['code'], 'admin_required')
        generate_url.assert_not_called()

    @patch('backend.services.auth_service.User.get_by_id')
    @patch('backend.services.auth_service.LoginLink.mark_used')
    @patch('backend.services.auth_service.Tenant.get_by_id')
    @patch('backend.services.auth_service.LoginLink.get_by_token')
    def test_login_link_rejects_mismatched_company_code(
        self,
        get_by_token,
        get_tenant,
        mark_used,
        get_user_by_id,
    ):
        tenant_id = ObjectId()
        get_by_token.return_value = {
            'token': 'company-token',
            'tenant_id': tenant_id,
            'user_id': self.user.id,
            'one_time': True,
            'expires_at': None,
            'revoked_at': None,
            'used_at': None,
        }
        get_tenant.return_value = {
            '_id': tenant_id,
            'company_code': 'acme',
            'is_active': True,
        }

        response = self.client.get(
            '/login-link/company-token?company_code=other&format=json'
        )

        self.assertEqual(response.status_code, 403)
        get_user_by_id.assert_not_called()
        mark_used.assert_not_called()

    @patch('backend.services.auth_service.User.update_login')
    @patch('backend.services.auth_service.User.get_by_id')
    @patch('backend.services.auth_service.LoginLink.mark_used')
    @patch('backend.services.auth_service.LoginLink.get_by_token')
    def test_frontend_can_exchange_login_link_for_authenticated_session(
        self,
        get_by_token,
        mark_used,
        get_user_by_id,
        update_login,
    ):
        get_by_token.return_value = {
            'token': 'direct-login-token',
            'user_id': self.user.id,
            'one_time': True,
            'expires_at': None,
            'revoked_at': None,
            'used_at': None,
        }
        get_user_by_id.return_value = self.user

        response = self.client.get(
            '/login-link/direct-login-token?format=json',
            headers={
                'Accept': 'application/json',
                'Origin': 'http://frontend.example:3000',
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['user']['username'], 'alice')
        self.assertEqual(payload['redirect'], '/portal')
        self.assertIn('session=', response.headers.get('Set-Cookie', ''))
        self.assertEqual(
            response.headers.get('Access-Control-Allow-Origin'),
            'http://frontend.example:3000',
        )
        self.assertEqual(
            response.headers.get('Access-Control-Allow-Credentials'),
            'true',
        )
        mark_used.assert_called_once_with('direct-login-token')
        update_login.assert_called_once_with(self.user.id)


if __name__ == '__main__':
    unittest.main()
