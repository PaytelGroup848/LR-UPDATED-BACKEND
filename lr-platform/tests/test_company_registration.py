import unittest
from unittest.mock import Mock, patch

from bson import ObjectId

from backend.services.tenant_registration_service import (
    TenantRegistrationError,
    TenantRegistrationService,
)


class CompanyRegistrationTests(unittest.TestCase):
    def _registration_patches(self):
        tenant_id = ObjectId()
        admin_id = ObjectId()
        tenant = {
            "_id": tenant_id,
            "company_name": "Acme Remote",
            "company_code": "acme01",
            "company_slug": "acme-remote",
            "registration_status": "pending",
            "is_active": False,
        }
        admin = {
            "_id": admin_id,
            "tenant_id": tenant_id,
            "username": "owner@example.com",
            "email": "owner@example.com",
            "role": "Admin",
            "is_active": True,
        }
        finalized_tenant = dict(
            tenant,
            admin_user_id=admin_id,
            registration_status="active",
            is_active=True,
        )
        return tenant, admin, finalized_tenant

    @patch("backend.services.tenant_registration_service.RegistrationRateLimitService.check_and_record", return_value=True)
    @patch("backend.services.tenant_registration_service.hash_password", return_value="hashed")
    @patch("backend.services.tenant_registration_service.User.create")
    @patch("backend.services.tenant_registration_service.User.collection")
    @patch("backend.services.tenant_registration_service.Tenant.get_by_id")
    @patch("backend.services.tenant_registration_service.Tenant.create_pending")
    @patch("backend.services.tenant_registration_service.Tenant.collection")
    def test_registers_company_without_any_license_key(
        self,
        tenant_collection,
        create_pending,
        get_tenant,
        user_collection,
        create_user,
        _hash_password,
        _rate_limit,
    ):
        tenant, admin, finalized_tenant = self._registration_patches()
        tenant_collection.find_one.return_value = None
        tenant_collection.update_one.return_value = Mock(modified_count=1)
        user_collection.find_one.return_value = None
        create_pending.return_value = tenant
        create_user.return_value = admin
        get_tenant.return_value = finalized_tenant

        result = TenantRegistrationService.register({
            "company_name": "Acme Remote",
            "company_code": "Acme01",
            "email": "Owner@Example.com",
            "password": "password123",
            "confirm_password": "password123",
        })

        create_user.assert_called_once_with(
            "owner@example.com",
            "hashed",
            "Admin",
            tenant_id=tenant["_id"],
            email="owner@example.com",
        )
        create_pending.assert_called_once()
        self.assertEqual(create_pending.call_args.args[:2], ("Acme Remote", "acme01"))
        update = tenant_collection.update_one.call_args.args[1]["$set"]
        self.assertNotIn("license_status", update)
        self.assertNotIn("license_key_reference", update)
        self.assertNotIn("license", result)
        self.assertEqual(result["admin"]["username"], "owner@example.com")

    @patch("backend.services.tenant_registration_service.RegistrationRateLimitService.check_and_record", return_value=True)
    def test_confirm_password_must_match(self, _rate_limit):
        with self.assertRaisesRegex(
            TenantRegistrationError,
            "Password and confirm password do not match",
        ):
            TenantRegistrationService.register({
                "company_name": "Acme Remote",
                "company_code": "acme01",
                "email": "owner@example.com",
                "password": "password123",
                "confirm_password": "different123",
            })

    @patch("backend.services.tenant_registration_service.RegistrationRateLimitService.check_and_record", return_value=True)
    def test_confirm_password_is_required(self, _rate_limit):
        with self.assertRaisesRegex(TenantRegistrationError, "Confirm password is required"):
            TenantRegistrationService.register({
                "company_name": "Acme Remote",
                "company_code": "acme01",
                "email": "owner@example.com",
                "password": "password123",
            })

    @patch("backend.services.tenant_registration_service.RegistrationRateLimitService.check_and_record", return_value=True)
    def test_company_code_is_required_and_validated(self, _rate_limit):
        with self.assertRaisesRegex(TenantRegistrationError, "Company code must be 3-32"):
            TenantRegistrationService.register({
                "company_name": "Acme Remote",
                "email": "owner@example.com",
                "password": "password123",
                "confirm_password": "password123",
            })

    @patch("backend.services.tenant_registration_service.RegistrationRateLimitService.check_and_record", return_value=True)
    @patch("backend.services.tenant_registration_service.Tenant.get_by_code")
    def test_duplicate_company_code_is_rejected(self, get_by_code, _rate_limit):
        get_by_code.return_value = {"company_code": "acme01"}
        with self.assertRaises(TenantRegistrationError) as caught:
            TenantRegistrationService.register({
                "company_name": "Different Display Name",
                "company_code": "ACME01",
                "email": "owner@example.com",
                "password": "password123",
                "confirm_password": "password123",
            })
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.code, "company_code_exists")


if __name__ == "__main__":
    unittest.main()
