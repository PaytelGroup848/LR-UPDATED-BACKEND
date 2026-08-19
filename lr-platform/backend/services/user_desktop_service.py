import logging
from bson import ObjectId

from backend.models.application import PublishedApp
from backend.models.assignment import ApplicationAssignment
from backend.services.remote_app_service import RemoteAppService

logger = logging.getLogger(__name__)


def _clean_text(value):
    return str(value or "").strip()


def _windows_username(user):
    val = _clean_text(user.get("windows_username") or user.get("username"))
    if "\\" in val:
        val = val.rsplit("\\", 1)[-1]
    if "@" in val:
        val = val.split("@", 1)[0]
    return val


def _object_id(value):
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return None


class UserDesktopService:
    @classmethod
    def register_user_desktop(cls, user, server_id=None, bypass_existence_check=False):
        """
        Automatically registers the Windows Desktop folder item for a newly created user,
        publishes it to RDS via RemoteAppService, and assigns it exclusively to that user.
        """
        try:
            if not user or not isinstance(user, dict):
                return None

            user_id = str(user.get("_id") or user.get("id") or "")
            if not user_id:
                return None

            win_username = _windows_username(user)
            if not win_username:
                return None

            tenant_id = user.get("tenant_id")
            target_server_id = (
                server_id
                or user.get("windows_server_id")
                or user.get("server_id")
                or user.get("default_server_id")
            )

            desktop_path = f"C:\\Users\\{win_username}\\Desktop"
            try:
                os.makedirs(desktop_path, exist_ok=True)
            except Exception:
                pass
            target_slug = f"desktop-{win_username.lower()}-{user_id[-6:] if len(user_id) >= 6 else user_id}"

            query: dict[str, object] = {
                "$or": [
                    {"folder_path": desktop_path},
                    {"slug": target_slug},
                ]
            }
            if tenant_id:
                query["tenant_id"] = _object_id(tenant_id) or tenant_id

            existing_app = PublishedApp.collection.find_one(query)

            if existing_app:
                app_id = str(existing_app["_id"])
                # Ensure alias is explorer so RDS launches ||explorer cleanly
                PublishedApp.collection.update_one(
                    {"_id": existing_app["_id"]},
                    {
                        "$set": {
                            "remote_app_alias": "explorer",
                            "remote_app_program": "||explorer",
                            "remote_app_file_path": r"C:\Windows\explorer.exe",
                            "remote_app_working_dir": desktop_path,
                            "working_directory": desktop_path,
                            "folder_permission": "write",
                            "initial_program": "explorer.exe",
                            "target": desktop_path,
                            "folder_path": desktop_path,
                            "arguments": desktop_path,
                            "remote_app_publish_status": "published",
                        }
                    }
                )
                app = PublishedApp.collection.find_one({"_id": existing_app["_id"]})
            else:
                raw_payload = {
                    "server_id": _object_id(target_server_id) if target_server_id else None,
                    "name": "Desktop",
                    "slug": target_slug,
                    "icon": "folder",
                    "item_type": "folder",
                    "display_mode": "remote_app",
                    "launch_mode": "initial_program",
                    "target": desktop_path,
                    "folder_path": desktop_path,
                    "folder_permission": "write",
                    "initial_program": "explorer.exe",
                    "remote_app_file_path": r"C:\Windows\explorer.exe",
                    "remote_app_working_dir": desktop_path,
                    "working_directory": desktop_path,
                    "arguments": desktop_path,
                    "remote_app_alias": "explorer",
                    "remote_app_program": "||explorer",
                    "remote_app_publish_status": "published",
                    "description": f"Windows Desktop for {win_username}",
                    "is_active": True,
                }
                normalized_payload = RemoteAppService.normalize_app_fields(raw_payload)
                normalized_payload["remote_app_alias"] = "explorer"
                normalized_payload["remote_app_program"] = "||explorer"
                normalized_payload["remote_app_publish_status"] = "published"
                created_app = PublishedApp.create(normalized_payload, tenant_id=tenant_id)
                if not created_app:
                    created_app = PublishedApp.collection.find_one(query)
                if not created_app:
                    logger.warning(f"Could not create PublishedApp for Desktop at {desktop_path}")
                    return None
                app = created_app
                app_id = str(app["_id"])

                # Trigger RemoteApp RDS sync/publishing for the newly registered Desktop item
                try:
                    RemoteAppService.sync_app(app)
                except Exception as sync_err:
                    logger.warning(f"RDS sync for Desktop item {app_id} skipped: {sync_err}")

                PublishedApp.collection.update_one({"_id": app["_id"]}, {"$set": {"remote_app_publish_status": "published", "remote_app_alias": "explorer", "remote_app_program": "||explorer"}})

            # Make available ONLY to this user via ApplicationAssignment
            existing_assignment = ApplicationAssignment.find(user_id, app_id, tenant_id=tenant_id)
            if not existing_assignment:
                ApplicationAssignment.assign(
                    user_id=user_id,
                    app_id=app_id,
                    is_default=False,
                    tenant_id=tenant_id
                )

            return app_id
        except Exception as error:
            logger.exception(f"Error during isolated user desktop registration for user {user.get('username')}: {error}")
            return None
