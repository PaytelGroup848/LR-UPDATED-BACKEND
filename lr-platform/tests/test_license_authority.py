import importlib.util
import json
import os
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch


os.environ.setdefault("MONGODB_URL", "mongodb://127.0.0.1:27017")
MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "services"
    / "license-authority"
    / "app"
    / "main.py"
)
SPEC = importlib.util.spec_from_file_location("lr_license_authority_test_module", MODULE_PATH)
license_authority = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(license_authority)


class _FakeLicenses:
    def __init__(self, document):
        self.document = dict(document)
        self.claim_filter = None

    def find_one(self, query):
        if "key" in query:
            return dict(self.document) if query["key"] == self.document["key"] else None
        return dict(self.document) if query.get("_id") == self.document["_id"] else None

    def find_one_and_update(self, query, update, return_document=None):
        self.claim_filter = query
        if (
            query.get("_id") != self.document["_id"]
            or self.document.get("status") != "unassigned"
        ):
            return None
        self.document.update(update["$set"])
        return dict(self.document)

    def update_one(self, query, update):
        if query.get("_id") == self.document["_id"]:
            self.document.update(update["$set"])


class LicenseAuthorityTests(unittest.TestCase):
    def test_unassigned_key_is_atomically_claimed_and_accepted(self):
        expires_at = datetime.utcnow() + timedelta(days=365)
        fake = _FakeLicenses({
            "_id": "key-id",
            "key": "LR-FRESH",
            "status": "unassigned",
            "expiresAt": expires_at,
        })

        with patch.object(license_authority, "licenses", fake):
            result = license_authority.validate_key(
                license_authority.LicenseValidationRequest(key="  lr-fresh  ")
            )

        self.assertTrue(result["data"]["valid"])
        self.assertEqual(result["data"]["status"], "active")
        self.assertEqual(fake.document["status"], "active")
        self.assertEqual(fake.claim_filter["status"], "unassigned")
        self.assertIn("$gt", fake.claim_filter["expiresAt"])

    def test_expired_unassigned_key_is_not_claimed(self):
        fake = _FakeLicenses({
            "_id": "key-id",
            "key": "LR-EXPIRED",
            "status": "unassigned",
            "expiresAt": datetime.utcnow() - timedelta(seconds=1),
        })

        with patch.object(license_authority, "licenses", fake):
            result = license_authority.validate_key(
                license_authority.LicenseValidationRequest(key="LR-EXPIRED")
            )

        self.assertFalse(result["data"]["valid"])
        self.assertEqual(result["data"]["status"], "expired")
        self.assertIsNone(fake.claim_filter)

    def test_health_returns_degraded_when_ping_fails(self):
        admin = Mock()
        admin.command.side_effect = RuntimeError("db down")
        client = Mock(admin=admin)

        with patch.object(license_authority, "client", client):
            response = license_authority.health()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            json.loads(response.body),
            {
                "service": "license-authority",
                "status": "degraded",
                "database": "unavailable",
                "error": "db down",
            },
        )


if __name__ == "__main__":
    unittest.main()
