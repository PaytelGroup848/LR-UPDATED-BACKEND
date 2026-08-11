import os
import re
from datetime import datetime
from uuid import uuid4

from bson import ObjectId
from flask import current_app

from backend.models.application import PublishedApp
from backend.models.assignment import ApplicationAssignment
from backend.models.user import User
from backend.models.server import Server
from backend.tenancy.context import scoped_filter
from backend.services.desktop_shortcut_service import DesktopShortcutService
from backend.services.remote_app_service import RemoteAppService


def _object_id(value):
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return None


def _slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return slug or "app"


def _as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"false", "0", "no", "off"}


def _app_response(app):
    tenant_id = app.get("tenant_id")
    data = PublishedApp.to_dict(app)
    assignment_query = {
        "app_id": {"$in": [_object_id(app.get("_id")), str(app.get("_id"))]},
        "is_enabled": True,
    }
    if tenant_id:
        assignment_query = scoped_filter(tenant_id, assignment_query)
    assignments = list(ApplicationAssignment.collection.find(assignment_query))
    users = []
    for assignment in assignments:
        user = User.get_by_id(assignment.get("user_id"), tenant_id=tenant_id)
        if user:
            users.append(User.to_dict(user))
    data["assigned_users"] = users
    return data


def _is_remote_app(app):
    item_type = str((app or {}).get("item_type") or "").strip().lower()
    # Folders are published through Explorer as RemoteApps. They used to be
    # excluded here, so an assigned folder could never launch in Remote App view.
    return item_type != "desktop"


def _tenant_for_user(user_id):
    user = User.get_by_id(user_id) if user_id else None
    return user.get("tenant_id") if user else None


def _sync_message(base_message, sync_result):
    if not sync_result:
        return base_message
    if sync_result.get("success"):
        return f"{base_message} RemoteApp sync completed."
    state = sync_result.get("status") or "failed"
    detail = sync_result.get("message") or "RemoteApp sync did not complete."
    return f"{base_message} RemoteApp sync is {state}: {detail}"


class ApplicationService:

    @staticmethod
    def list_apps(user_id=None):
        tenant_id = _tenant_for_user(user_id)
        query = scoped_filter(tenant_id) if tenant_id else {}
        apps = PublishedApp.collection.find(query).sort("name", 1)
        return {
            "success": True,
            "apps": [_app_response(app) for app in apps],
        }

    @staticmethod
    def create_app(data, user_id, ip_address):
        tenant_id = _tenant_for_user(user_id)
        name = str(data.get("name") or "").strip()
        server_id = data.get("server_id")

        if not name or not server_id:
            return {"success": False, "message": "Name and server are required"}, 400
        if tenant_id and not Server.get_by_id(server_id, tenant_id):
            return {"success": False, "message": "Server not found"}, 404

        payload = dict(data)
        payload["slug"] = payload.get("slug") or _slugify(name)
        payload["is_active"] = _as_bool(payload.get("is_active"), True)
        if _is_remote_app(payload):
            payload = RemoteAppService.normalize_app_fields(payload)
            payload["remote_app_publish_status"] = (
                "pending" if payload.get("is_active") else "unpublished"
            )

        app = PublishedApp.create(payload, tenant_id=tenant_id)
        if not app:
            return {"success": False, "message": "Published item already exists"}, 409

        sync_result = RemoteAppService.sync_app(app) if _is_remote_app(app) else None
        app = PublishedApp.get_by_id(app.get("_id"), tenant_id) or app
        return {
            "success": True,
            "message": _sync_message("Item saved successfully.", sync_result),
            "app": _app_response(app),
            "remote_app_sync": sync_result,
        }, 201

    @staticmethod
    def update_app(app_id, data, user_id, ip_address):
        tenant_id = _tenant_for_user(user_id)
        app = PublishedApp.get_by_id(app_id, tenant_id)
        if not app:
            return {"success": False, "message": "Published item not found"}, 404
        previous = dict(app)

        updates = dict(data)
        if "name" in updates and not updates.get("slug"):
            updates["slug"] = _slugify(updates.get("name"))
        if "is_active" in updates:
            updates["is_active"] = _as_bool(updates.get("is_active"), True)
        merged = {**previous, **updates}
        if _is_remote_app(merged):
            updates = RemoteAppService.normalize_app_fields(updates, existing=previous)
            alias_query = {
                "remote_app_alias": updates.get("remote_app_alias"),
                "_id": {"$ne": _object_id(app_id)},
            }
            if tenant_id:
                alias_query = scoped_filter(tenant_id, alias_query)
            alias_owner = PublishedApp.collection.find_one(alias_query)
            if alias_owner:
                return {"success": False, "message": "RemoteApp alias is already in use"}, 409

        PublishedApp.update(app_id, updates, tenant_id)
        app = PublishedApp.get_by_id(app_id, tenant_id)

        sync_result = None
        cleanup_result = None
        previous_remote = _is_remote_app(previous)
        current_remote = _is_remote_app(app)
        previous_active = previous.get("is_active") is not False
        current_active = app.get("is_active") is not False

        identity_changed = RemoteAppService.identity_changed(previous, app) if current_remote else True
        if previous_remote and (not current_remote or (previous_active and not current_active)):
            cleanup_result = RemoteAppService.unpublish_app(
                previous,
                update_config=current_remote and not identity_changed,
            )
            sync_result = cleanup_result
        elif previous_remote and current_remote and current_active and identity_changed:
            cleanup_result = RemoteAppService.unpublish_app(previous, record_result=False)
            sync_result = RemoteAppService.publish_app(app)
        elif current_remote and current_active:
            sync_result = RemoteAppService.publish_app(app)
        elif current_remote:
            previous_status = str(previous.get("remote_app_publish_status") or "").lower()
            if previous_status in {"pending", "failed", "published"}:
                sync_result = RemoteAppService.unpublish_app(app)
            else:
                sync_result = RemoteAppService.mark_inactive(app)

        app = PublishedApp.get_by_id(app_id, tenant_id) or app

        message = _sync_message("Item updated successfully.", sync_result)
        if cleanup_result and cleanup_result is not sync_result and not cleanup_result.get("success"):
            cleanup_detail = cleanup_result.get("message") or "Previous RemoteApp cleanup is pending."
            message = f"{message} Previous RemoteApp cleanup is pending: {cleanup_detail}"
        return {
            "success": True,
            "message": message,
            "app": _app_response(app),
            "remote_app_sync": sync_result,
            "remote_app_cleanup": cleanup_result if cleanup_result is not sync_result else None,
        }, 200

    @staticmethod
    def delete_app(app_id, user_id, ip_address):
        tenant_id = _tenant_for_user(user_id)
        app = PublishedApp.get_by_id(app_id, tenant_id)
        if not app:
            return {"success": False, "message": "Published item not found"}, 404

        should_unpublish = (
            _is_remote_app(app)
            and str(app.get("remote_app_publish_status") or "").lower() != "unpublished"
        )
        sync_result = RemoteAppService.unpublish_app(app) if should_unpublish else None
        result = PublishedApp.delete(app_id, tenant_id)
        if not result or result.deleted_count == 0:
            return {"success": False, "message": "Published item not found"}, 404

        app_oid = _object_id(app_id)
        assignment_query = {
            "app_id": {"$in": [app_oid, str(app_id)] if app_oid else [str(app_id)]}
        }
        if tenant_id:
            assignment_query = scoped_filter(tenant_id, assignment_query)
        ApplicationAssignment.collection.delete_many(assignment_query)

        return {
            "success": True,
            "message": _sync_message("Item deleted successfully.", sync_result),
            "remote_app_sync": sync_result,
        }, 200

    @staticmethod
    def retry_remote_app(app_id, user_id, ip_address):
        tenant_id = _tenant_for_user(user_id)
        app = PublishedApp.get_by_id(app_id, tenant_id)
        if not app:
            return {"success": False, "message": "Published item not found"}, 404
        if not _is_remote_app(app):
            return {"success": False, "message": "This item is not a RemoteApp application"}, 400

        sync_result = RemoteAppService.retry_app(app)
        app = PublishedApp.get_by_id(app_id, tenant_id) or app
        return {
            "success": bool(sync_result.get("success")),
            "message": _sync_message("RemoteApp retry finished.", sync_result),
            "app": _app_response(app),
            "remote_app_sync": sync_result,
        }, 200

    @staticmethod
    def assign_app(app_id, data, user_id, ip_address):
        tenant_id = _tenant_for_user(user_id)
        target_user_id = data.get("user_id")
        default_provided = "is_default" in data
        is_default = _as_bool(data.get("is_default"), False)
        app = PublishedApp.get_by_id(app_id, tenant_id)
        if not app:
            return {"success": False, "message": "Published item not found"}, 404
        target_user = User.get_by_id(target_user_id, tenant_id=tenant_id)
        if not target_user:
            return {"success": False, "message": "User not found"}, 404

        existing = ApplicationAssignment.find(target_user_id, app_id, tenant_id)
        if existing:
            updates = {"is_enabled": True, "assigned_at": datetime.utcnow()}
            if default_provided:
                updates["is_default"] = is_default
            ApplicationAssignment.collection.update_one(
                {"_id": existing["_id"]},
                {"$set": updates},
            )
            assignment = ApplicationAssignment.collection.find_one({"_id": existing["_id"]})
        else:
            assignment = ApplicationAssignment.assign(target_user_id, app_id, is_default=is_default, tenant_id=tenant_id)

        if is_default:
            ApplicationAssignment.set_default(target_user_id, app_id)
            assignment = ApplicationAssignment.find(target_user_id, app_id, tenant_id)

        sync_result = None
        if _is_remote_app(app) and str(app.get("remote_app_publish_status")).lower() != "published":
            sync_result = RemoteAppService.publish_app(app)

        shortcut_result = DesktopShortcutService.sync_assignment_shortcut(target_user, app)
        return {
            "success": True,
            "message": "Assignment saved",
            "assignment": ApplicationAssignment.to_dict(assignment),
            "shortcut": shortcut_result,
            "remote_app_sync": sync_result,
        }, 200

    @staticmethod
    def user_assignments(user_id, admin_user_id=None):
        tenant_id = _tenant_for_user(admin_user_id)
        user = User.get_by_id(user_id, tenant_id=tenant_id)
        if not user:
            return {"success": False, "message": "User not found"}, 404

        user_oid = _object_id(user_id)
        user_ids = [str(user_id)]
        if user_oid:
            user_ids.append(user_oid)

        assignment_query = {
            "user_id": {"$in": user_ids},
            "is_enabled": True,
        }
        if tenant_id:
            assignment_query = scoped_filter(tenant_id, assignment_query)
        assignments = list(ApplicationAssignment.collection.find(assignment_query))
        assigned_app_ids = [str(item.get("app_id")) for item in assignments if item.get("app_id")]

        return {
            "success": True,
            "user": User.to_dict(user),
            "assigned_app_ids": assigned_app_ids,
            "assignments": [ApplicationAssignment.to_dict(item) for item in assignments],
            "available_apps": PublishedApp.to_dict_list(PublishedApp.collection.find(
                scoped_filter(tenant_id, {"is_active": True}) if tenant_id else {"is_active": True}
            ).sort("name", 1)),
        }, 200

    @staticmethod
    def bulk_assign_apps(user_ids, app_ids, enabled, admin_user_id, ip_address):
        changed = 0
        for user_id in user_ids or []:
            for app_id in app_ids or []:
                if enabled:
                    result, status = ApplicationService.assign_app(app_id, {"user_id": user_id}, admin_user_id, ip_address)
                    if status == 200 and result.get("success"):
                        changed += 1
                else:
                    result, status = ApplicationService.unassign_app(app_id, user_id, admin_user_id, ip_address)
                    if status == 200 and result.get("success"):
                        changed += 1

        return {
            "success": True,
            "message": "Assignments updated",
            "changed": changed,
        }

    @staticmethod
    def upload_software(uploaded_file, admin_user_id, ip_address):
        if not uploaded_file:
            return {
                "success": False,
                "error": "file is required"
            }, 400

        filename = os.path.basename(uploaded_file.filename or "")

        if not filename.lower().endswith((".exe", ".msi", ".bat", ".cmd")):
            return {
                "success": False,
                "error": "Only executable installer files are allowed"
            }, 400

        upload_dir = os.path.join(
            current_app.instance_path,
            "software_uploads"
        )
        os.makedirs(upload_dir, exist_ok=True)

        stored_name = (
            f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            f"-{uuid4().hex[:8]}"
            f"-{filename}"
        )
        file_path = os.path.join(upload_dir, stored_name)

        uploaded_file.save(file_path)

        return {
            "success": True,
            "file": {
                "name": stored_name,
                "path": file_path,
                "size": os.path.getsize(file_path)
            }
        }, 201

    @staticmethod
    def unassign_app(app_id, user_id, admin_user_id, ip_address):
        tenant_id = _tenant_for_user(admin_user_id)
        assignment = ApplicationAssignment.find(user_id, app_id, tenant_id)
        if not assignment:
            return {"success": False, "message": "Assignment not found"}, 404

        user = User.get_by_id(user_id, tenant_id=tenant_id)
        app = PublishedApp.get_by_id(app_id, tenant_id)
        delete_query = {"_id": assignment["_id"]}
        if tenant_id:
            delete_query = scoped_filter(tenant_id, delete_query)
        ApplicationAssignment.collection.delete_one(delete_query)
        shortcut_result = (
            DesktopShortcutService.remove_assignment_shortcut(user, app)
            if user and app
            else {"success": False, "message": "Shortcut sync skipped.", "skipped": True}
        )
        return {"success": True, "message": "Assignment removed", "shortcut": shortcut_result}, 200


AppService = ApplicationService
