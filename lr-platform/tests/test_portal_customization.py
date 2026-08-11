import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bson import ObjectId
from flask import Flask
from flask_login import LoginManager
from werkzeug.datastructures import FileStorage

from backend.api.routers.portal_customization_route import portal_customization_bp
from backend.models.portal_customization import PortalCustomization, default_portal_config
from backend.models.user import MongoUser
from backend.services.portal_customization_service import (
    PortalCustomizationError,
    PortalCustomizationService,
    validate_portal_updates,
)
from backend.services.index_service import IndexService


class _FakeIndexCollection:
    def __init__(self, indexes=None):
        self.indexes = indexes or {}
        self.created = []
        self.dropped = []

    def index_information(self):
        return self.indexes

    def create_index(self, keys, **options):
        self.created.append((keys, options))

    def drop_index(self, name):
        self.dropped.append(name)


class _FakeIndexDatabase:
    def __init__(self):
        self.collections = {}
        self.users = self["users"]
        self.portal_customizations = self["portal_customizations"]

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = _FakeIndexCollection()
        return self.collections[name]


class PortalCustomizationValidationTests(unittest.TestCase):
    def test_valid_values_are_normalized(self):
        result = validate_portal_updates({
            "primary_color": "#12ABef",
            "login_card_width": "480",
            "show_logo": "true",
            "support_url": "https://support.example.com/help",
        })

        self.assertEqual(result["primary_color"], "#12abef")
        self.assertEqual(result["login_card_width"], 480)
        self.assertTrue(result["show_logo"])

    def test_invalid_colour_and_unsafe_text_are_rejected(self):
        with self.assertRaises(PortalCustomizationError):
            validate_portal_updates({"primary_color": "green"})
        with self.assertRaises(PortalCustomizationError):
            validate_portal_updates({"welcome_heading": "<script>alert(1)</script>"})

    def test_only_http_urls_are_allowed(self):
        with self.assertRaises(PortalCustomizationError):
            validate_portal_updates({"support_url": "javascript:alert(1)"})

    def test_unsupported_forgot_password_cannot_be_enabled(self):
        with self.assertRaises(PortalCustomizationError):
            validate_portal_updates({"show_forgot_password": True})

    def test_unknown_fields_are_rejected(self):
        with self.assertRaises(PortalCustomizationError):
            validate_portal_updates({"tenant_id": str(ObjectId())})


class PortalCustomizationModelTests(unittest.TestCase):
    def test_get_always_scopes_by_tenant_and_state(self):
        tenant_id = ObjectId()
        with patch.object(PortalCustomization, "collection") as collection:
            collection.find_one.return_value = None
            PortalCustomization.get(tenant_id, "draft")

        collection.find_one.assert_called_once_with({
            "state": "draft",
            "tenant_id": tenant_id,
        })

    def test_index_setup_replaces_non_unique_tenant_state_index(self):
        fake_db = _FakeIndexDatabase()
        fake_db.portal_customizations.indexes = {
            "legacy_tenant_state": {
                "key": [("tenant_id", 1), ("state", 1)],
                "unique": False,
            }
        }
        IndexService._ensured = False
        try:
            with patch("backend.services.index_service.db", fake_db):
                IndexService.ensure_indexes()
        finally:
            IndexService._ensured = False

        self.assertIn("legacy_tenant_state", fake_db.portal_customizations.dropped)
        self.assertIn(
            (
                [("tenant_id", 1), ("state", 1)],
                {
                    "unique": True,
                    "name": "uq_portal_customization_tenant_state",
                },
            ),
            fake_db.portal_customizations.created,
        )


class PortalCustomizationServiceTests(unittest.TestCase):
    def setUp(self):
        self.tenant_id = ObjectId()
        self.actor = MongoUser({
            "_id": ObjectId(),
            "tenant_id": self.tenant_id,
            "username": "admin",
            "role": "Admin",
            "is_active": True,
        })

    @patch("backend.services.portal_customization_service.AuditService.log")
    @patch.object(PortalCustomization, "save_draft")
    @patch.object(PortalCustomization, "get")
    def test_saving_draft_does_not_publish(self, get_config, save_draft, _audit):
        get_config.return_value = None
        saved_config = default_portal_config()
        saved_config["company_name"] = "Acme"
        save_draft.return_value = {
            "tenant_id": self.tenant_id,
            "state": "draft",
            "version": 1,
            "config": saved_config,
        }

        response = PortalCustomizationService.save_draft(
            self.actor,
            {"company_name": "Acme"},
        )

        self.assertEqual(response["settings"]["config"]["company_name"], "Acme")
        save_draft.assert_called_once()
        self.assertEqual(save_draft.call_args.args[0], self.tenant_id)

    @patch("backend.services.portal_customization_service.AuditService.log")
    @patch.object(PortalCustomization, "publish")
    @patch.object(PortalCustomization, "get")
    def test_publish_copies_the_tenant_draft(self, get_config, publish, _audit):
        draft_config = default_portal_config()
        draft_config["portal_title"] = "Acme Portal"
        get_config.return_value = {
            "tenant_id": self.tenant_id,
            "state": "draft",
            "version": 3,
            "config": draft_config,
        }
        published_config = dict(draft_config)
        publish.return_value = {
            "tenant_id": self.tenant_id,
            "state": "published",
            "version": 2,
            "config": published_config,
        }

        response = PortalCustomizationService.publish(self.actor)

        self.assertEqual(response["settings"]["config"]["portal_title"], "Acme Portal")
        self.assertEqual(publish.call_args.args[0], self.tenant_id)
        self.assertEqual(publish.call_args.args[1]["portal_title"], "Acme Portal")

    @patch("backend.services.portal_customization_service.Tenant.get_by_code")
    def test_unknown_company_gets_safe_defaults(self, get_tenant):
        get_tenant.return_value = None

        response = PortalCustomizationService.public_settings("unknown")

        self.assertFalse(response["company_resolved"])
        self.assertFalse(response["published"])
        self.assertEqual(response["config"]["portal_title"], "LR Remote Access")
        self.assertNotIn("logo_asset", response["config"])

    @patch.object(PortalCustomization, "get")
    @patch("backend.services.portal_customization_service.Tenant.get_by_code")
    def test_public_settings_read_published_state_only(self, get_tenant, get_config):
        get_tenant.return_value = {"_id": self.tenant_id, "is_active": True}
        published = default_portal_config()
        published["company_name"] = "Public Acme"
        published["logo_asset"] = "a" * 32 + ".png"
        get_tenant.return_value["company_code"] = "acme"
        get_config.return_value = {
            "tenant_id": self.tenant_id,
            "state": "published",
            "version": 4,
            "config": published,
        }

        response = PortalCustomizationService.public_settings("acme")

        get_config.assert_called_once_with(self.tenant_id, "published")
        self.assertEqual(response["config"]["company_name"], "Public Acme")
        self.assertIn("/assets/acme/", response["config"]["logo_url"])
        self.assertNotIn(str(self.tenant_id), response["config"]["logo_url"])
        self.assertNotIn("updated_by", response)

    @patch("backend.services.portal_customization_service.AuditService.log")
    def test_executable_content_disguised_as_png_is_rejected(self, _audit):
        upload = FileStorage(
            stream=io.BytesIO(b"MZ" + b"not-an-image"),
            filename="logo.png",
            content_type="image/png",
        )

        with self.assertRaises(PortalCustomizationError):
            PortalCustomizationService.upload_asset(self.actor, "logo", upload)

    @patch("backend.services.portal_customization_service.AuditService.log")
    def test_oversized_logo_is_rejected(self, _audit):
        upload = FileStorage(
            stream=io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * (2 * 1024 * 1024)),
            filename="logo.png",
            content_type="image/png",
        )

        with self.assertRaises(PortalCustomizationError):
            PortalCustomizationService.upload_asset(self.actor, "logo", upload)

    @patch("backend.services.portal_customization_service.AuditService.log")
    @patch.object(PortalCustomization, "save_draft")
    @patch.object(PortalCustomization, "get")
    def test_reset_restores_defaults_without_publishing(self, get_config, save_draft, _audit):
        current = default_portal_config()
        current["company_name"] = "Custom"
        get_config.return_value = {"config": current}
        save_draft.return_value = {
            "tenant_id": self.tenant_id,
            "state": "draft",
            "version": 7,
            "config": default_portal_config(),
        }

        response = PortalCustomizationService.reset_draft(self.actor)

        self.assertEqual(response["settings"]["config"]["company_name"], "LR Remote Access")
        self.assertEqual(save_draft.call_args.args[1], default_portal_config())

    @patch("backend.services.portal_customization_service.AuditService.log")
    @patch.object(PortalCustomization, "save_draft")
    @patch.object(PortalCustomization, "get")
    def test_valid_asset_is_stored_inside_tenant_directory(
        self,
        get_config,
        save_draft,
        _audit,
    ):
        get_config.side_effect = [None, None, None]
        saved = default_portal_config()
        save_draft.side_effect = lambda tenant_id, config, updated_by=None: {
            "tenant_id": tenant_id,
            "state": "draft",
            "version": 1,
            "config": config,
        }
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        upload = FileStorage(
            stream=io.BytesIO(png),
            filename="logo.png",
            content_type="image/png",
        )

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(PortalCustomizationService, "storage_root", Path(directory)):
                response = PortalCustomizationService.upload_asset(
                    self.actor,
                    "logo",
                    upload,
                )
                stored = list((Path(directory) / str(self.tenant_id)).glob("*.png"))

        self.assertEqual(len(stored), 1)
        self.assertTrue(response["settings"]["config"]["logo_url"].endswith(".png"))


class PortalCustomizationRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY="portal-test")
        login_manager = LoginManager(self.app)
        self.user = MongoUser({
            "_id": ObjectId(),
            "tenant_id": ObjectId(),
            "username": "operator",
            "role": "User",
            "is_active": True,
        })

        @login_manager.user_loader
        def load_user(_user_id):
            return self.user

        self.app.register_blueprint(portal_customization_bp)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = self.user.id
            session["_fresh"] = True

    @patch.object(PortalCustomizationService, "save_draft")
    def test_non_admin_cannot_change_portal(self, save_draft):
        response = self.client.put(
            "/api/admin/portal-customization/draft",
            json={"company_name": "Blocked"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["code"], "admin_required")
        save_draft.assert_not_called()

    @patch.object(PortalCustomizationService, "get_draft")
    def test_admin_can_read_draft(self, get_draft):
        self.user["role"] = "Admin"
        get_draft.return_value = {"success": True, "settings": {"version": 2}}

        response = self.client.get("/api/admin/portal-customization/draft")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["settings"]["version"], 2)

    @patch.object(PortalCustomizationService, "save_draft")
    def test_admin_can_change_portal_draft(self, save_draft):
        self.user["role"] = "Admin"
        save_draft.return_value = {"success": True, "settings": {"version": 1}}

        response = self.client.put(
            "/api/admin/portal-customization/draft",
            json={"company_name": "Allowed"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        save_draft.assert_called_once()


if __name__ == "__main__":
    unittest.main()
