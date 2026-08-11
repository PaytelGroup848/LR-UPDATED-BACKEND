from backend.models.application import PublishedApp
from backend.models.assignment import ApplicationAssignment
from backend.models.server import Server
from backend.models.user import User
from backend.services.portal_service import PortalService


def _resource_type(app):
    item_type = str((app or {}).get("item_type") or "").strip().lower()
    if item_type == "folder" or (app or {}).get("folder_path"):
        return "folder"
    return "application"


def _resource_icon(app, resource_type):
    icon = str((app or {}).get("icon") or "").strip()
    if icon.startswith(("/", "http://", "https://")):
        return icon
    return "/lr-icons/folder.svg" if resource_type == "folder" else "/lr-icons/application.svg"


def _resource_payload(app):
    resource_type = _resource_type(app)
    return {
        "id": str(app.get("_id")),
        "name": app.get("name") or ("Folder" if resource_type == "folder" else "Application"),
        "icon": _resource_icon(app, resource_type),
        "type": resource_type,
    }


def _is_published_remote_app(app):
    item_type = str((app or {}).get("item_type") or "").strip().lower()
    publish_status = str((app or {}).get("remote_app_publish_status") or "").strip().lower()
    return item_type not in {"desktop", "folder"} and publish_status != "unpublished"


def _is_published_folder(app):
    publish_status = str((app or {}).get("remote_app_publish_status") or "").strip().lower()
    return _resource_type(app) == "folder" and publish_status != "unpublished"


def _id_text(value):
    if isinstance(value, dict):
        value = value.get("id") or value.get("_id") or value.get("app_id")
    return str(value or "").strip()


def _assigned_server_for_user(user):
    user_id = _id_text((user or {}).get("_id") or (user or {}).get("id"))
    tenant_id = (user or {}).get("tenant_id")
    mapped_server_id = _id_text(
        (user or {}).get("windows_server_id") or (user or {}).get("default_server_id")
    )
    if mapped_server_id:
        server = Server.get_by_id(mapped_server_id, tenant_id)
        if not server or server.get("is_active") is False:
            return None, "The Windows server assigned to this user is unavailable", 404
        return server, None, 200

    assigned_apps = PublishedApp.assigned_to_user(user_id)
    if not assigned_apps:
        return None, "No server access is assigned to this user", 403

    apps_by_server = {}
    for app in assigned_apps:
        server_id = _id_text(app.get("server_id"))
        if server_id:
            apps_by_server.setdefault(server_id, []).append(app)
    if not apps_by_server:
        return None, "Assigned applications are missing server configuration", 400

    server_ids = list(apps_by_server)
    if len(server_ids) > 1:
        default_app_id = _id_text(
            (user or {}).get("default_application_id") or (user or {}).get("assigned_app")
        )
        default_server_id = ""
        for server_id, apps in apps_by_server.items():
            if any(_id_text(app.get("_id")) == default_app_id for app in apps):
                default_server_id = server_id
                break
        if not default_server_id:
            return None, "Assigned applications use multiple servers; configure a default application", 409
        server_ids = [default_server_id]

    server = Server.get_by_id(server_ids[0], tenant_id)
    if not server or server.get("is_active") is False:
        return None, "Assigned server is unavailable", 404
    return server, None, 200


class LrResourcesService:
    @staticmethod
    def select_login_remote_app(user):
        user_id = _id_text((user or {}).get("_id") or (user or {}).get("id"))
        assigned_apps = PublishedApp.assigned_to_user(user_id)
        if not assigned_apps:
            if ApplicationAssignment.for_user(user_id):
                return None, "Assigned RemoteApp is unavailable", 404
            return None, "No RemoteApp is assigned to this user", 403

        remote_apps = [app for app in assigned_apps if _is_published_remote_app(app)]
        if not remote_apps:
            return None, "Assigned application is missing its RemoteApp configuration", 400
        if len(remote_apps) == 1:
            return remote_apps[0], None, 200

        apps_by_id = {_id_text(app.get("_id")): app for app in remote_apps}

        configured_user_default = _id_text((user or {}).get("default_application_id"))
        if configured_user_default:
            default_app = apps_by_id.get(configured_user_default)
            if default_app:
                return default_app, None, 200
            if ApplicationAssignment.find(user_id, configured_user_default):
                return None, "Configured default RemoteApp is unavailable", 404
            return None, "Configured default RemoteApp is not assigned to this user", 403

        legacy_default = _id_text((user or {}).get("assigned_app"))
        if legacy_default in apps_by_id:
            return apps_by_id[legacy_default], None, 200

        default_ids = {
            _id_text(assignment.get("app_id"))
            for assignment in ApplicationAssignment.defaults_for_user(user_id)
            if _id_text(assignment.get("app_id")) in apps_by_id
        }
        if len(default_ids) == 1:
            return apps_by_id[next(iter(default_ids))], None, 200
        if len(default_ids) > 1:
            return None, "Multiple default RemoteApps are configured for this user", 409
        return None, "Multiple RemoteApps are assigned; configure a default application", 409

    @staticmethod
    def launch_default_remote_app(user, ip_address, user_agent):
        app, error, status_code = LrResourcesService.select_login_remote_app(user)
        if error:
            return {"success": False, "error": error}, status_code

        user_id = _id_text((user or {}).get("_id") or (user or {}).get("id"))
        launch, status_code = PortalService.launch_native_remote_app(
            app_id=app.get("_id"),
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        if status_code != 200 or not launch.get("success"):
            return {
                "success": False,
                "error": launch.get("error") or "RemoteApp session could not be created",
            }, status_code
        if not launch.get("rdp_file_url") or not launch.get("session_id"):
            return {
                "success": False,
                "error": "RemoteApp session did not return an RDP file",
            }, 500

        app_id = _id_text(app.get("_id"))
        return {
            "success": True,
            "connection_type": "remoteapp",
            "launch_transport": "rdp_remote_app",
            "rdp_file_url": launch.get("rdp_file_url"),
            "session_id": launch.get("session_id"),
            "resource_id": app_id,
            "default_application_id": app_id,
            "application_name": app.get("name") or "RemoteApp",
        }, 200

    @staticmethod
    def launch_assigned_web_desktop(user, ip_address, user_agent):
        user_id = _id_text((user or {}).get("_id") or (user or {}).get("id"))
        server, error, status_code = _assigned_server_for_user(user)
        if error:
            return {"success": False, "error": error}, status_code

        launch, status_code = PortalService.launch_server(
            data={"server_id": server.get("_id"), "view_mode": "html5"},
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        if status_code != 200 or not launch.get("success"):
            return {
                "success": False,
                "error": launch.get("error") or "Web desktop session could not be created",
            }, status_code

        launch_url = launch.get("launch_url") or launch.get("client_url")
        if not launch_url:
            return {
                "success": False,
                "error": launch.get("warning") or "Web desktop gateway did not return a launch URL",
            }, 502

        return {
            "success": True,
            "connection_type": "web",
            "launch_transport": "html5",
            "launch_url": launch_url,
            "session_id": launch.get("session_id"),
            "server_id": _id_text(server.get("_id")),
            "server_name": server.get("name") or "Remote Desktop",
        }, 200

    @staticmethod
    def launch_assigned_native_desktop(user, ip_address, user_agent):
        user_id = _id_text((user or {}).get("_id") or (user or {}).get("id"))
        server, error, status_code = _assigned_server_for_user(user)
        if error:
            return {"success": False, "error": error}, status_code

        launch, status_code = PortalService.launch_native_desktop(
            server_id=server.get("_id"),
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        if status_code != 200 or not launch.get("success"):
            return {
                "success": False,
                "error": launch.get("error") or "Desktop RDP session could not be created",
            }, status_code
        if not launch.get("rdp_file_url") or not launch.get("session_id"):
            return {
                "success": False,
                "error": "Desktop RDP session did not return an RDP file",
            }, 500

        return {
            "success": True,
            "connection_type": "desktop",
            "launch_transport": "rdp_desktop",
            "rdp_file_url": launch.get("rdp_file_url"),
            "session_id": launch.get("session_id"),
            "server_id": _id_text(server.get("_id")),
            "server_name": server.get("name") or "Remote Desktop",
        }, 200

    @staticmethod
    def my_resources(user_id):
        assigned_apps = PublishedApp.assigned_to_user(user_id)
        resources = [
            _resource_payload(app)
            for app in assigned_apps
            if _is_published_remote_app(app) or _is_published_folder(app)
        ]
        return {
            "success": True,
            "logo": "/lr-remote-logo.png",
            "applications": [item for item in resources if item["type"] == "application"],
            "folders": [item for item in resources if item["type"] == "folder"],
        }, 200

    @staticmethod
    def launch_resource(data, user_id, ip_address, user_agent):
        resource_id = str((data or {}).get("resource_id") or "").strip()
        requested_type = str((data or {}).get("type") or "").strip().lower()
        connection_type = str((data or {}).get("connection_type") or "").strip().lower()
        if connection_type != "remoteapp":
            return {"success": False, "error": "connection_type must be remoteapp"}, 400
        if not resource_id:
            return {"success": False, "error": "resource_id is required"}, 400
        if requested_type not in {"application", "folder"}:
            return {"success": False, "error": "type must be application or folder"}, 400

        user = User.get_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}, 404

        app = PublishedApp.get_by_id(resource_id, user.get("tenant_id"))
        if not app:
            return {"success": False, "error": "Resource not found"}, 404

        actual_type = _resource_type(app)
        if actual_type != requested_type:
            return {"success": False, "error": "Resource type mismatch"}, 400

        if requested_type == "application" and not _is_published_remote_app(app):
            return {"success": False, "error": "RemoteApp configuration is incomplete."}, 422
        if requested_type == "folder" and not _is_published_folder(app):
            return {"success": False, "error": "RemoteApp configuration is incomplete."}, 422

        return PortalService.launch_remote_app(
            app_id=resource_id,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
