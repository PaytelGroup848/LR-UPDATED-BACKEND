from datetime import datetime
from bson import ObjectId
from backend.extensions import db
from backend.tenancy.context import scoped_filter, tenant_document


def _object_id(value):
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return None


def _display_mode_from_launch_mode(app):
    launch_mode = app.get("launch_mode")
    if launch_mode == "desktop":
        return "full_desktop"
    if launch_mode in {"remote_app", "initial_program"}:
        return "remote_app"
    return "html5"


class PublishedApp:

    collection = db["published_apps"]
    servers_collection = db["servers"]
    assignments_collection = db["application_assignments"]

    @staticmethod
    def create(data, tenant_id=None):

        app = {
            "server_id": _object_id(data.get("server_id")),
            "name": data.get("name"),
            "slug": data.get("slug"),
            "icon": data.get("icon", "app"),
            "item_type": data.get("item_type"),
            "display_mode": data.get("display_mode") or data.get("view_mode"),
            "target": data.get("target"),
            "folder_path": data.get("folder_path"),
            "folder_permission": data.get("folder_permission"),
            "launch_mode": data.get("launch_mode", "remote_app"),
            "remote_app_alias": data.get("remote_app_alias"),
            "remote_app_program": data.get("remote_app_program"),
            "remote_app_file_path": data.get("remote_app_file_path"),
            "remote_app_source_file_path": data.get("remote_app_source_file_path"),
            "remote_app_managed_file_path": data.get("remote_app_managed_file_path"),
            "remote_app_files_staged": bool(data.get("remote_app_files_staged")),
            "remote_app_publication_mode": data.get("remote_app_publication_mode"),
            "initial_program": data.get("initial_program"),
            "rds_collection_name": data.get("rds_collection_name"),
            "rds_connection_broker": data.get("rds_connection_broker"),
            "remote_app_publish_status": data.get("remote_app_publish_status"),
            "remote_app_publish_message": data.get("remote_app_publish_message", ""),
            "working_directory": data.get("working_directory"),
            "arguments": data.get("arguments"),
            "description": data.get("description", ""),
            "is_active": data.get("is_active", True),
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        if tenant_id is not None:
            app = tenant_document(tenant_id, app)

        unique_checks = [{"slug": app["slug"]}]
        if app.get("remote_app_alias"):
            unique_checks.append({"remote_app_alias": app["remote_app_alias"]})
        unique_query = {"$or": unique_checks}
        if tenant_id is not None:
            unique_query = scoped_filter(tenant_id, unique_query)
        if PublishedApp.collection.find_one(unique_query):
            return None

        result = PublishedApp.collection.insert_one(app)
        app["_id"] = result.inserted_id
        return app

    @staticmethod
    def get_by_id(app_id, tenant_id=None):
        object_id = _object_id(app_id)
        if not object_id:
            return None
        query = {"_id": object_id}
        return PublishedApp.collection.find_one(scoped_filter(tenant_id, query) if tenant_id is not None else query)

    @staticmethod
    def assigned_to_user(user_id, tenant_id=None):
        oid = _object_id(user_id)
        user_ids = [str(user_id)]
        if oid:
            user_ids.append(oid)

        assignments = list(
            PublishedApp.assignments_collection.find(scoped_filter(tenant_id, {
                "user_id": {"$in": user_ids},
                "is_enabled": True
            }) if tenant_id is not None else {
                "user_id": {"$in": user_ids}, "is_enabled": True
            })
    )

        app_ids = []

        for a in assignments:
            app_id = _object_id(a.get("app_id"))
            if app_id:
                app_ids.append(app_id)

        return list(
            PublishedApp.collection.find(scoped_filter(tenant_id, {
                "_id": {"$in": app_ids},
                "is_active": True
            }) if tenant_id is not None else {"_id": {"$in": app_ids}, "is_active": True}).sort("name", 1)
    )

    @staticmethod
    def update(app_id, data, tenant_id=None):
        object_id = _object_id(app_id)
        if not object_id:
            return None

        if "server_id" in data:
            data["server_id"] = _object_id(data.get("server_id"))
        data["updated_at"] = datetime.utcnow()

        data.pop("tenant_id", None)
        query = {"_id": object_id}
        if tenant_id is not None:
            query = scoped_filter(tenant_id, query)
        return PublishedApp.collection.update_one(
            query,
            {"$set": data}
        )

    @staticmethod
    def delete(app_id, tenant_id=None):
        object_id = _object_id(app_id)
        if not object_id:
            return None
        query = {"_id": object_id}
        return PublishedApp.collection.delete_one(scoped_filter(tenant_id, query) if tenant_id is not None else query)

    @staticmethod
    def to_dict(app, include_server=True):

        data = {
            "id": str(app.get("_id")),
            "tenant_id": str(app.get("tenant_id")) if app.get("tenant_id") else None,
            "server_id": str(app.get("server_id")) if app.get("server_id") else None,
            "name": app.get("name"),
            "slug": app.get("slug"),
            "icon": app.get("icon"),
            "item_type": app.get("item_type") or app.get("launch_mode"),
            "display_mode": app.get("display_mode") or _display_mode_from_launch_mode(app),
            "target": app.get("target") or app.get("remote_app_program") or app.get("folder_path"),
            "folder_path": app.get("folder_path"),
            "folder_permission": app.get("folder_permission"),
            "launch_mode": app.get("launch_mode"),
            "remote_app_alias": app.get("remote_app_alias"),
            "remote_app_program": app.get("remote_app_program"),
            "remote_app_file_path": app.get("remote_app_file_path"),
            "remote_app_source_file_path": app.get("remote_app_source_file_path"),
            "remote_app_managed_file_path": app.get("remote_app_managed_file_path"),
            "remote_app_files_staged": bool(app.get("remote_app_files_staged")),
            "remote_app_publication_mode": app.get("remote_app_publication_mode"),
            "initial_program": app.get("initial_program"),
            "rds_collection_name": app.get("rds_collection_name"),
            "rds_connection_broker": app.get("rds_connection_broker"),
            "remote_app_publish_status": app.get("remote_app_publish_status"),
            "remote_app_publish_message": app.get("remote_app_publish_message", ""),
            "remote_app_last_sync_at": app.get("remote_app_last_sync_at").isoformat() if app.get("remote_app_last_sync_at") else None,
            "remote_app_published_at": app.get("remote_app_published_at").isoformat() if app.get("remote_app_published_at") else None,
            "remote_app_unpublished_at": app.get("remote_app_unpublished_at").isoformat() if app.get("remote_app_unpublished_at") else None,
            "working_directory": app.get("working_directory"),
            "arguments": app.get("arguments"),
            "description": app.get("description", ""),
            "is_active": app.get("is_active"),
            "created_at": app.get("created_at").isoformat() if app.get("created_at") else None,
            "updated_at": app.get("updated_at").isoformat() if app.get("updated_at") else None,
        }

        if include_server and app.get("server_id"):
            server_query = {"_id": app["server_id"]}
            if app.get("tenant_id"):
                server_query["tenant_id"] = app["tenant_id"]
            server = PublishedApp.servers_collection.find_one(server_query)
            if server:
                data["server"] = {
                    "id": str(server.get("_id")),
                    "name": server.get("name"),
                    "ip_address": server.get("host"),
                    "rdp_port": server.get("port"),
                    "agent_id": server.get("agent_id"),
                    "rds_collection_name": server.get("rds_collection_name"),
                    "rds_connection_broker": server.get("rds_connection_broker"),
                    "is_active": server.get("is_active"),
                }
                data["server_name"] = server.get("name")

        return data

    @classmethod
    def to_dict_list(cls, apps, include_server=True):
        if not apps:
            return []
        apps = list(apps)
        if not include_server:
            return [cls.to_dict(a, include_server=False) for a in apps]

        server_ids = list({a.get("server_id") for a in apps if a.get("server_id")})
        servers_by_id = {}
        if server_ids:
            found_servers = list(cls.servers_collection.find({"_id": {"$in": server_ids}}))
            for s in found_servers:
                servers_by_id[str(s["_id"])] = s

        result = []
        for app in apps:
            data = cls.to_dict(app, include_server=False)
            sid = str(app.get("server_id")) if app.get("server_id") else None
            server = servers_by_id.get(sid) if sid else None
            if server:
                data["server"] = {
                    "id": str(server.get("_id")),
                    "name": server.get("name"),
                    "ip_address": server.get("host"),
                    "rdp_port": server.get("port"),
                    "agent_id": server.get("agent_id"),
                    "rds_collection_name": server.get("rds_collection_name"),
                    "rds_connection_broker": server.get("rds_connection_broker"),
                    "is_active": server.get("is_active"),
                }
                data["server_name"] = server.get("name")
            result.append(data)
        return result
