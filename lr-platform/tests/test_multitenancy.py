import unittest
from unittest.mock import Mock, patch

from bson import ObjectId
from flask import Flask

from backend.core.error_handlers import register_error_handlers
from backend.models.user import MongoUser, User
from backend.printing.registry import SessionRegistry
from backend.services.access_policy_service import AccessPolicyService
from backend.tenancy.context import TenantScopeError, scoped_filter


class TenantScopeTests(unittest.TestCase):
    def test_missing_tenant_returns_controlled_response(self):
        app = Flask(__name__)
        register_error_handlers(app)

        @app.get("/tenant-required")
        def tenant_required():
            raise TenantScopeError("Authenticated user is not assigned to a tenant")

        response = app.test_client().get("/tenant-required")

        self.assertEqual(response.status_code, 423)
        self.assertEqual(response.get_json()["code"], "tenant_required")

    def test_client_cannot_override_tenant_filter(self):
        tenant_a = ObjectId()
        tenant_b = ObjectId()
        with self.assertRaises(TenantScopeError):
            scoped_filter(tenant_a, {"tenant_id": tenant_b, "status": "active"})

    def test_user_lookup_pins_id_and_tenant(self):
        tenant_id = ObjectId()
        user_id = ObjectId()
        with patch.object(User, "collection") as collection:
            collection.find_one.return_value = None
            User.get_by_id(user_id, tenant_id=tenant_id)
        collection.find_one.assert_called_once_with({"_id": user_id, "tenant_id": tenant_id})

    def test_tenant_admin_cannot_view_other_tenant_session(self):
        tenant_id = ObjectId()
        user = MongoUser({"_id": ObjectId(), "tenant_id": tenant_id, "role": "Admin", "is_active": True})
        session_id = ObjectId()
        with patch("backend.services.access_policy_service.RdpSession.collection") as collection:
            collection.find_one.return_value = None
            allowed, reason, session = AccessPolicyService.can_view_session(user, session_id)
        self.assertFalse(allowed)
        self.assertIsNone(session)
        collection.find_one.assert_called_once_with({"_id": session_id, "tenant_id": tenant_id})


class PrintingTenantIsolationTests(unittest.TestCase):
    def test_same_session_and_connection_are_isolated_by_tenant(self):
        registry = SessionRegistry()
        registry.register_print_client("session", "connection", "user-a", tenant_id="tenant-a")
        registry.register_print_client("session", "connection", "user-b", tenant_id="tenant-b")

        self.assertEqual(
            registry.get_print_client("session", "connection", tenant_id="tenant-a").user_id,
            "user-a",
        )
        self.assertEqual(
            registry.get_print_client("session", "connection", tenant_id="tenant-b").user_id,
            "user-b",
        )
        self.assertIsNone(registry.get_print_client("session", "connection", tenant_id="tenant-c"))


if __name__ == "__main__":
    unittest.main()
