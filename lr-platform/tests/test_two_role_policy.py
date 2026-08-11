import unittest

from backend.database.migrate_two_roles import canonical_user_role
from backend.models.role import Role
from backend.models.user import User


class TwoRolePolicyTests(unittest.TestCase):
    def test_only_admin_and_user_are_valid_roles(self):
        self.assertEqual(User.ROLES, ("Admin", "User"))
        self.assertEqual(
            Role.DEFAULT_ROLES,
            [
                {"id": 1, "name": "ADMIN", "description": "Platform access"},
                {"id": 4, "name": "USER", "description": "Standard user access"},
            ],
        )
        self.assertEqual(User.normalize_role("ADMIN"), "Admin")
        self.assertEqual(User.normalize_role("user"), "User")

        for legacy_role in ("Super Admin", "SUPER_ADMIN", "Manager", "Viewer"):
            with self.assertRaises(ValueError):
                User.normalize_role(legacy_role)

    def test_admin_has_only_admin_permissions(self):
        self.assertTrue(User.has_role({"role": "Admin"}, "Admin"))
        self.assertFalse(User.has_role({"role": "Admin"}, "User"))
        self.assertFalse(User.has_role({"role": "User"}, "Admin"))
        self.assertTrue(User.has_role({"role": "User"}, "User"))

    def test_migration_maps_legacy_roles(self):
        for legacy_admin in ("Admin", "ADMIN", "Super Admin", "SUPER_ADMIN", "superadmin"):
            self.assertEqual(canonical_user_role(legacy_admin), "Admin")

        for standard_user in ("User", "USER", "Manager", "Viewer", None, ""):
            self.assertEqual(canonical_user_role(standard_user), "User")


if __name__ == "__main__":
    unittest.main()
