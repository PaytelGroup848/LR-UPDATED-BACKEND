import unittest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import requests
from pymongo.errors import DuplicateKeyError

from backend.models.license import LicenseActivation
from backend.models.license import ProductKey
from backend.services.external_license_validator import (
    ExternalLicenseValidation,
    ExternalLicenseValidator,
    LicenseServerUnavailable,
)
from backend.services.license_service import LicenseService
from backend.services import user_license_service as user_license_module


class ExternalLicenseValidatorTests(unittest.TestCase):
    def setUp(self):
        self.validator = ExternalLicenseValidator(
            "https://licenses.example.test/public/keys/validate",
            timeout_seconds=10,
        )

    @patch("backend.services.external_license_validator.requests.post")
    def test_valid_key_returns_exact_expiry(self, post):
        response = Mock()
        response.json.return_value = {
            "success": True,
            "data": {
                "valid": True,
                "status": "active",
                "expiresAt": "2027-07-20T00:00:00.000Z",
            },
        }
        post.return_value = response

        result = self.validator.validate("LR-VALID")

        self.assertEqual(result.expires_at, datetime(2027, 7, 20))
        post.assert_called_once_with(
            "https://licenses.example.test/public/keys/validate",
            json={"key": "LR-VALID"},
            timeout=10.0,
        )
        response.raise_for_status.assert_called_once_with()

    @patch("backend.services.external_license_validator.requests.post")
    def test_invalid_statuses_have_clear_messages(self, post):
        for status, message in (
            ("not_found", "LR-Key was not found."),
            ("suspended", "LR-Key is suspended."),
            ("expired", "LR-Key has expired."),
        ):
            with self.subTest(status=status):
                response = Mock()
                response.json.return_value = {
                    "success": True,
                    "data": {"valid": False, "status": status},
                }
                post.return_value = response
                with self.assertRaisesRegex(ValueError, message):
                    self.validator.validate("LR-INVALID")

    @patch("backend.services.external_license_validator.requests.post")
    def test_network_failure_is_reported_without_unlocking(self, post):
        post.side_effect = requests.exceptions.ConnectionError("offline")

        with self.assertRaisesRegex(LicenseServerUnavailable, "Could not reach"):
            self.validator.validate("LR-KEY")

    @patch("backend.services.external_license_validator.requests.post")
    def test_plain_http_is_rejected_before_key_is_sent(self, post):
        validator = ExternalLicenseValidator(
            "http://210.56.147.241/public/keys/validate"
        )

        with self.assertRaisesRegex(LicenseServerUnavailable, "must use HTTPS"):
            validator.validate("LR-SECRET")
        post.assert_not_called()

    @patch("backend.services.external_license_validator.requests.post")
    def test_internal_authority_http_is_allowed(self, post):
        validator = ExternalLicenseValidator(
            "http://license-authority:8005/public/keys/validate"
        )
        response = Mock()
        response.json.return_value = {
            "success": True,
            "data": {
                "valid": True,
                "status": "active",
                "expiresAt": "2027-07-22T00:00:00.000Z",
            },
        }
        post.return_value = response

        result = validator.validate("LR-INTERNAL")

        self.assertEqual(result.status, "active")
        post.assert_called_once()


class _KeyRepository:
    def __init__(self):
        self.key = None

    def get_by_code(self, key_code):
        if self.key and self.key.key_code == key_code:
            return self.key
        return None

    def create(self, product_key):
        product_key._id = "key-id"
        self.key = product_key
        return product_key


class _ActivationRepository:
    def __init__(self):
        self.activation = None

    def get_active_for_key(self, _product_key_id):
        return self.activation

    def create(self, activation: LicenseActivation):
        activation._id = "activation-id"
        self.activation = activation
        return activation

    def update_expiry(self, activation, expires_at):
        activation.expires_at = expires_at
        return activation

    def deactivate_for_key(self, _product_key_id, _when):
        self.activation = None


class _TrialRepository:
    @staticmethod
    def get_by_device(_device_id):
        return None


class ExternalLicenseActivationTests(unittest.TestCase):
    @patch("backend.services.license_service.AuditService.log")
    @patch.object(LicenseService, "_signed_token", return_value="signed-token")
    def test_valid_external_key_is_imported_with_api_expiry(self, _token, _audit):
        expiry = datetime(2027, 7, 20)
        validator = Mock()
        validator.validate.return_value = ExternalLicenseValidation(expiry)
        keys = _KeyRepository()
        activations = _ActivationRepository()
        service = LicenseService(
            key_repository=keys,
            activation_repository=activations,
            trial_repository=_TrialRepository(),
            external_validator=validator,
        )

        result = service.activate(
            key_code="LR-VALID",
            device_id="user:123",
            device_name="alice",
        )

        self.assertEqual(result["status"], "LICENSED")
        self.assertEqual(result["expires_at"], expiry)
        self.assertEqual(activations.activation.expires_at, expiry)
        self.assertEqual(keys.key.source, "external")
        validator.validate.assert_called_once_with("LR-VALID")

    @patch("backend.services.license_service.AuditService.log")
    @patch.object(LicenseService, "_signed_token", return_value="signed-token")
    def test_external_key_is_normalized_before_lookup_and_validation(self, _token, _audit):
        expiry = datetime(2027, 7, 20)
        validator = Mock()
        validator.validate.return_value = ExternalLicenseValidation(expiry)
        keys = _KeyRepository()
        service = LicenseService(
            key_repository=keys,
            activation_repository=_ActivationRepository(),
            trial_repository=_TrialRepository(),
            external_validator=validator,
        )

        result = service.activate(
            key_code="  lr-valid  ",
            device_id="user:123",
            device_name="alice",
        )

        self.assertEqual(result["status"], "LICENSED")
        self.assertEqual(keys.key.key_code, "LR-VALID")
        validator.validate.assert_called_once_with("LR-VALID")

    @patch("backend.services.license_service.AuditService.log")
    def test_concurrent_activation_loser_is_rejected(self, _audit):
        expiry = datetime(2027, 7, 20)
        product_key = ProductKey(
            key_code="LR-RACE",
            source="external",
            external_expires_at=expiry,
        )
        product_key._id = "key-id"
        keys = _KeyRepository()
        keys.key = product_key
        winner = LicenseActivation(
            product_key_id="key-id",
            device_id="user:winner",
            expires_at=expiry,
        )
        activations = Mock()
        activations.get_active_for_key.side_effect = [None, winner]
        activations.create.side_effect = DuplicateKeyError("duplicate")
        validator = Mock()
        validator.validate.return_value = ExternalLicenseValidation(expiry)
        service = LicenseService(
            key_repository=keys,
            activation_repository=activations,
            trial_repository=_TrialRepository(),
            external_validator=validator,
        )

        with self.assertRaisesRegex(ValueError, "already assigned"):
            service.activate(
                key_code="LR-RACE",
                device_id="user:loser",
                device_name="bob",
            )

    def test_active_trial_is_allowed_even_if_legacy_hold_flag_exists(self):
        activations = Mock()
        activations.get_by_device.return_value = None
        trials = Mock()
        trials.get_by_device.return_value = Mock(
            is_held=True,
            expires_at=datetime.utcnow() + timedelta(days=3),
        )
        service = LicenseService(
            key_repository=Mock(),
            activation_repository=activations,
            trial_repository=trials,
            external_validator=Mock(),
        )

        result = service.get_status("user:123")

        self.assertEqual(result["status"], "TRIAL_ACTIVE")
        self.assertGreaterEqual(result["days_remaining"], 3)


class SevenDayTrialGateTests(unittest.TestCase):
    @patch.object(user_license_module.UserLicenseService, "is_bypass_user", return_value=False)
    @patch.object(user_license_module.User, "get_id", return_value="user-id")
    @patch.object(user_license_module, "_license_service")
    def test_trial_window_starts_at_user_creation_time(
        self,
        service_factory,
        _get_id,
        _is_bypass,
    ):
        created_at = datetime(2026, 7, 21, 10, 30)
        repository = service_factory.return_value.trial_repository
        repository.get_by_device.return_value = None
        repository.create.side_effect = lambda trial: trial

        trial = user_license_module.UserLicenseService.ensure_trial({
            "_id": "user-id",
            "username": "alice",
            "created_at": created_at,
        })

        self.assertEqual(trial.started_at, created_at)
        self.assertEqual(trial.expires_at, datetime(2026, 7, 28, 10, 30))

    @patch.object(user_license_module.UserLicenseService, "ensure_trial")
    @patch.object(user_license_module.UserLicenseService, "is_bypass_user", return_value=False)
    @patch.object(user_license_module.User, "get_id", return_value="user-id")
    @patch.object(
        user_license_module,
        "_created_at_for_user",
        return_value=datetime(2026, 7, 21),
    )
    @patch.object(user_license_module, "_license_service")
    def test_active_trial_allows_access_without_a_key(
        self,
        service_factory,
        _created_at,
        _get_id,
        _is_bypass,
        _ensure_trial,
    ):
        service_factory.return_value.get_status.return_value = {
            "status": "TRIAL_ACTIVE",
            "expires_at": datetime(2026, 7, 28),
            "days_remaining": 7,
        }

        result = user_license_module.UserLicenseService.get_status(
            {"_id": "user-id", "username": "alice"}
        )

        self.assertFalse(result["blocked"])
        self.assertNotIn("message", result)

    @patch.object(user_license_module.UserLicenseService, "ensure_trial")
    @patch.object(user_license_module.UserLicenseService, "is_bypass_user", return_value=False)
    @patch.object(user_license_module.User, "get_id", return_value="user-id")
    @patch.object(
        user_license_module,
        "_created_at_for_user",
        return_value=datetime(2026, 7, 21),
    )
    @patch.object(user_license_module, "_license_service")
    def test_expired_trial_requires_an_admin_assigned_key(
        self,
        service_factory,
        _created_at,
        _get_id,
        _is_bypass,
        _ensure_trial,
    ):
        service_factory.return_value.get_status.return_value = {
            "status": "TRIAL_EXPIRED",
            "expires_at": datetime(2026, 7, 28),
            "days_remaining": 0,
        }

        result = user_license_module.UserLicenseService.get_status(
            {"_id": "user-id", "username": "alice"}
        )

        self.assertTrue(result["blocked"])
        self.assertEqual(
            result["message"],
            "Your license is not active. Contact your administrator.",
        )


if __name__ == "__main__":
    unittest.main()
