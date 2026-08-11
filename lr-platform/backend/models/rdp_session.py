from datetime import datetime
from backend.extensions import db


_UNRESOLVED_APP_NAME = object()


class RdpSession:

    collection = db["rdp_sessions"]
    apps_collection = db["published_apps"]

    @staticmethod
    def create(data):
        tenant_id = data.get("tenant_id")
        if tenant_id is None and data.get("user_id"):
            from backend.models.user import User
            user = User.get_by_id(data.get("user_id"))
            tenant_id = user.get("tenant_id") if user else None
        session = {
            "tenant_id": tenant_id,
            "user_id": data.get("user_id"),
            "server_id": data.get("server_id"),
            "published_app_id": data.get("published_app_id"),
            "guac_token": data.get("guac_token"),
            "guac_connection_id": data.get("guac_connection_id"),
            "launch_url": data.get("launch_url"),
            "reconnect_token": data.get("reconnect_token"),
            "connection_type": data.get("connection_type", "rdp"),
            "display_mode": data.get("display_mode"),
            "launch_mode": data.get("launch_mode"),
            "native_remote_app": bool(data.get("native_remote_app")),
            "rdp_file_expires_at": data.get("rdp_file_expires_at"),
            "rdp_file_downloaded_at": data.get("rdp_file_downloaded_at"),
            "browser_launch_nonce_hash": data.get("browser_launch_nonce_hash"),
            "browser_launch_expires_at": data.get("browser_launch_expires_at"),
            "browser_launch_used_at": data.get("browser_launch_used_at"),
            "windows_username": data.get("windows_username"),
            "windows_domain": data.get("windows_domain"),
            "session_isolation": data.get("session_isolation"),
            "is_isolated_session": bool(data.get("is_isolated_session")),
            "status": data.get("status", "active"),
            "ip_address": data.get("ip_address"),
            "user_agent": data.get("user_agent"),
            "client_fingerprint": data.get("client_fingerprint"),
            "started_at": datetime.utcnow(),
            "reconnected_at": None,
            "last_seen_at": datetime.utcnow(),
            "ended_at": None
        }

        result = RdpSession.collection.insert_one(session)
        session["_id"] = result.inserted_id
        return session

    @staticmethod
    def to_dict(session, app_name=_UNRESOLVED_APP_NAME):

        duration = None
        if session.get("started_at"):
            end = session.get("ended_at") or datetime.utcnow()
            duration = int((end - session["started_at"]).total_seconds())

        if app_name is _UNRESOLVED_APP_NAME and session.get("published_app_id"):
            app_name = None
            app_query = {"_id": session["published_app_id"]}
            if session.get("tenant_id"):
                app_query["tenant_id"] = session["tenant_id"]
            app = RdpSession.apps_collection.find_one(app_query, {"name": 1})
            if app:
                app_name = app.get("name")
        elif app_name is _UNRESOLVED_APP_NAME:
            app_name = None

        payload = {
            "id": str(session.get("_id")),
            "tenant_id": str(session.get("tenant_id")) if session.get("tenant_id") else None,
            "user_id": str(session.get("user_id")) if session.get("user_id") else None,
            "server_id": str(session.get("server_id")) if session.get("server_id") else None,
            "published_app_id": str(session.get("published_app_id")) if session.get("published_app_id") else None,
            "published_app_name": app_name,
            "guac_connection_id": session.get("guac_connection_id"),
            "reconnect_available": session.get("status") in {"active", "pending"},
            "connection_type": session.get("connection_type"),
            "display_mode": session.get("display_mode"),
            "launch_mode": session.get("launch_mode"),
            "windows_username": session.get("windows_username"),
            "windows_domain": session.get("windows_domain"),
            "session_isolation": session.get("session_isolation"),
            "is_isolated_session": bool(session.get("is_isolated_session")),
            "status": session.get("status"),
            "ip_address": session.get("ip_address"),
            "user_agent": session.get("user_agent"),
            "started_at": session.get("started_at").isoformat() if session.get("started_at") else None,
            "reconnected_at": session.get("reconnected_at").isoformat() if session.get("reconnected_at") else None,
            "last_seen_at": session.get("last_seen_at").isoformat() if session.get("last_seen_at") else None,
            "ended_at": session.get("ended_at").isoformat() if session.get("ended_at") else None,
            "duration_seconds": duration,
        }
        if session.get("native_remote_app"):
            payload.update({
                "native_remote_app": True,
                "rdp_file_expires_at": session.get("rdp_file_expires_at").isoformat() if session.get("rdp_file_expires_at") else None,
                "rdp_file_downloaded_at": session.get("rdp_file_downloaded_at").isoformat() if session.get("rdp_file_downloaded_at") else None,
            })
        return payload

    @staticmethod
    def to_dict_many(sessions):
        items = list(sessions or [])
        app_ids = {item.get("published_app_id") for item in items if item.get("published_app_id")}
        names = {
            app["_id"]: app.get("name")
            for app in RdpSession.apps_collection.find(
                {"_id": {"$in": list(app_ids)}}, {"name": 1}
            )
        } if app_ids else {}
        return [
            RdpSession.to_dict(item, names.get(item.get("published_app_id")))
            for item in items
        ]

    @staticmethod
    def close(session_id):
        from bson import ObjectId

        return RdpSession.collection.update_one(
            {"_id": ObjectId(session_id)},
            {
                "$set": {
                    "status": "closed",
                    "ended_at": datetime.utcnow()
                }
            }
        )

    @staticmethod
    def ping(session_id):
        from bson import ObjectId

        return RdpSession.collection.update_one(
            {"_id": ObjectId(session_id)},
            {
                "$set": {
                    "last_seen_at": datetime.utcnow()
                }
            }
        )

    @staticmethod
    def get_active():
        return list(
            RdpSession.collection.find({"status": "active"})
            .sort("started_at", -1)
        )

    @staticmethod
    def get_by_user(user_id):
        return list(
            RdpSession.collection.find({"user_id": user_id})
            .sort("started_at", -1)
        )

    @staticmethod
    def get_active_by_user(user_id):
        return RdpSession.collection.find_one({
            "user_id": user_id,
            "status": "active"
        })
