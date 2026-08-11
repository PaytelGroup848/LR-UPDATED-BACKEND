import os

from bson import ObjectId

from backend.models.application import PublishedApp
from backend.models.assignment import ApplicationAssignment


def _object_id(value):
    try:
        return ObjectId(str(value))
    except Exception:
        return None


def _find_or_create_app(payload):
    existing = PublishedApp.collection.find_one({"slug": payload["slug"]})
    if existing:
        return existing
    return PublishedApp.create(payload)


def seed_lr_resources():
    user_id = _object_id(os.getenv("LR_SEED_USER_ID"))
    server_id = _object_id(os.getenv("LR_SEED_SERVER_ID"))
    if not user_id or not server_id:
        print("Skip LR resource seed: set LR_SEED_USER_ID and LR_SEED_SERVER_ID.")
        return

    busy_path = os.getenv("LR_SEED_BUSY_PATH", r"C:\BusyWin\Busy21.exe")
    folder_path = os.getenv("LR_SEED_FOLDER_PATH", r"C:\Users\Public\Desktop")

    resources = [
        {
            "server_id": server_id,
            "name": "Busy 21",
            "slug": "seed-busy-21",
            "icon": "/lr-icons/application.svg",
            "item_type": "application",
            "display_mode": "remote_app",
            "launch_mode": "initial_program",
            "target": busy_path,
            "initial_program": busy_path,
            "description": "Example assigned Busy 21 application",
            "is_active": True,
        },
        {
            "server_id": server_id,
            "name": "Desktop Folder",
            "slug": "seed-desktop-folder-read",
            "icon": "/lr-icons/folder.svg",
            "item_type": "folder",
            "display_mode": "remote_app",
            "launch_mode": "initial_program",
            "target": folder_path,
            "folder_path": folder_path,
            "folder_permission": "read",
            "initial_program": "explorer.exe",
            "arguments": folder_path,
            "description": "Example assigned desktop folder",
            "is_active": True,
        },
    ]

    for payload in resources:
        app = _find_or_create_app(payload)
        if app:
            ApplicationAssignment.assign(user_id, app["_id"])

    print("LR example resources seeded.")


if __name__ == "__main__":
    seed_lr_resources()
