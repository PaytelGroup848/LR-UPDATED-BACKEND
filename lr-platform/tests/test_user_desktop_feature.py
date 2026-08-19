import unittest
from bson import ObjectId

from backend.models.application import PublishedApp
from backend.models.assignment import ApplicationAssignment
from backend.services.user_desktop_service import UserDesktopService
from backend.services.lr_resources_service import LrResourcesService


class TestUserDesktopFeature(unittest.TestCase):
    def setUp(self):
        PublishedApp.collection.delete_many({})
        ApplicationAssignment.collection.delete_many({})

    def tearDown(self):
        PublishedApp.collection.delete_many({})
        ApplicationAssignment.collection.delete_many({})

    def test_desktop_registered_when_user_created(self):
        user_id = str(ObjectId())
        user = {
            "_id": ObjectId(user_id),
            "username": "demo1",
            "windows_username": "demo1",
            "windows_server_id": str(ObjectId()),
            "tenant_id": str(ObjectId()),
        }

        app_id = UserDesktopService.register_user_desktop(user)
        self.assertIsNotNone(app_id)

        # Check PublishedApp
        app = PublishedApp.collection.find_one({"_id": ObjectId(app_id)})
        self.assertIsNotNone(app)
        self.assertEqual(app["name"], "Desktop")
        self.assertEqual(app["item_type"], "folder")
        self.assertEqual(app["folder_path"], r"C:\Users\demo1\Desktop")
        self.assertEqual(app["target"], r"C:\Users\demo1\Desktop")
        self.assertEqual(app["initial_program"], "explorer.exe")
        self.assertEqual(app["arguments"], r"C:\Users\demo1\Desktop")
        self.assertEqual(app["remote_app_publish_status"], "published")

        # Check ApplicationAssignment
        assignment = ApplicationAssignment.find(user_id, app_id)
        self.assertIsNotNone(assignment)
        self.assertTrue(assignment.get("is_enabled"))

    def test_desktop_registration_prevents_duplicates(self):
        user_id = str(ObjectId())
        user = {
            "_id": ObjectId(user_id),
            "username": "demo2",
            "windows_username": "demo2",
            "tenant_id": str(ObjectId()),
        }

        app_id_1 = UserDesktopService.register_user_desktop(user)
        app_id_2 = UserDesktopService.register_user_desktop(user)

        self.assertEqual(app_id_1, app_id_2)
        count = PublishedApp.collection.count_documents({"folder_path": r"C:\Users\demo2\Desktop"})
        self.assertEqual(count, 1)

    def test_desktop_item_isolated_per_user(self):
        user1_id = str(ObjectId())
        user1 = {
            "_id": ObjectId(user1_id),
            "username": "user1",
            "windows_username": "user1",
            "tenant_id": str(ObjectId()),
        }

        user2_id = str(ObjectId())
        user2 = {
            "_id": ObjectId(user2_id),
            "username": "user2",
            "windows_username": "user2",
            "tenant_id": str(ObjectId()),
        }

        app1_id = UserDesktopService.register_user_desktop(user1)
        app2_id = UserDesktopService.register_user_desktop(user2)

        self.assertNotEqual(app1_id, app2_id)

        # my_resources for user1
        res1, code1 = LrResourcesService.my_resources(user1_id)
        self.assertEqual(code1, 200)
        user1_folder_ids = [f["id"] for f in res1.get("folders", [])]
        self.assertIn(app1_id, user1_folder_ids)
        self.assertNotIn(app2_id, user1_folder_ids)

        # my_resources for user2
        res2, code2 = LrResourcesService.my_resources(user2_id)
        self.assertEqual(code2, 200)
        user2_folder_ids = [f["id"] for f in res2.get("folders", [])]
        self.assertIn(app2_id, user2_folder_ids)
        self.assertNotIn(app1_id, user2_folder_ids)


if __name__ == "__main__":
    unittest.main()
