import unittest
from unittest.mock import Mock, patch

from backend.services.auth_service import _sync_windows_credentials_from_login
from backend.services.user_service import UserService


class WindowsAccountUpdateTests(unittest.TestCase):
    @patch('backend.services.auth_service.User.update')
    def test_login_does_not_overwrite_configured_windows_password(self, update):
        user = {
            '_id': 'user-id',
            'username': 'Himanshu',
            'windows_username': 'Himanshu',
            'windows_password': 'encrypted-windows-password',
        }

        _sync_windows_credentials_from_login(user, 'Himanshu', 'portal-password')

        update.assert_not_called()
        self.assertEqual(user['windows_password'], 'encrypted-windows-password')

    @patch('backend.services.user_service.encrypt_secret', return_value='encrypted-new-password')
    def test_bearer_user_update_persists_domain_and_encrypted_password(self, encrypt_secret):
        repository = Mock()
        repository.get_by_id.return_value = {
            '_id': 'user-id',
            'username': 'Himanshu',
            'windows_username': 'Himanshu',
            'windows_password': 'encrypted-old-password',
            'windows_account_enabled': True,
        }
        repository.update.side_effect = lambda user: user
        service = UserService(repository, Mock())

        updated = service.update_user('user-id', {
            'windows_domain': 'MYCOMPANY',
            'windows_password': 'actual-ad-password',
            'windows_account_enabled': True,
        })

        self.assertEqual(updated['windows_domain'], 'MYCOMPANY')
        self.assertEqual(updated['windows_password'], 'encrypted-new-password')
        encrypt_secret.assert_called_once_with('actual-ad-password')

    def test_empty_windows_password_keeps_existing_secret(self):
        repository = Mock()
        repository.get_by_id.return_value = {
            '_id': 'user-id',
            'username': 'Himanshu',
            'windows_username': 'Himanshu',
            'windows_password': 'encrypted-existing-password',
            'windows_account_enabled': True,
        }
        repository.update.side_effect = lambda user: user
        service = UserService(repository, Mock())

        updated = service.update_user('user-id', {
            'windows_domain': 'MYCOMPANY',
            'windows_password': '',
        })

        self.assertEqual(updated['windows_password'], 'encrypted-existing-password')
        self.assertEqual(updated['windows_domain'], 'MYCOMPANY')


if __name__ == '__main__':
    unittest.main()
