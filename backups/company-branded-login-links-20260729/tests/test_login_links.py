import unittest
from unittest.mock import patch

from bson import ObjectId
from flask import Flask
from flask_login import LoginManager

from backend.api.routers.auth_route import auth
from backend.core.app_factory import register_cors
from backend.models.user import MongoUser


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
        register_cors(self.app)
        self.client = self.app.test_client()

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
