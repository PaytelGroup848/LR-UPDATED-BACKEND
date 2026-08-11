from datetime import datetime
from backend.extensions import db


def _json_safe(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    try:
        from bson import ObjectId

        if isinstance(value, ObjectId):
            return str(value)
    except Exception:
        pass
    return value


class ActivityLog:

    collection = db["activity_logs"]

    @staticmethod
    def log(
        user_id=None,
        action=None,
        category=None,
        server_id=None,
        session_id=None,
        ip_address=None,
        success=True,
        reason=None,
        actor_role=None,
        metadata=None,
        tenant_id=None,
    ):
        now = datetime.utcnow()
        entry = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "action": action,
            "category": category,
            "server_id": server_id,
            "session_id": session_id,
            "ip_address": ip_address,
            "success": bool(success),
            "reason": reason,
            "actor_role": actor_role,
            "metadata": metadata or {},
            "timestamp": now,
            "created_at": now,
        }

        result = ActivityLog.collection.insert_one(entry)
        entry["_id"] = result.inserted_id
        return entry

    @staticmethod
    def recent(limit=100, user_id=None, tenant_id=None):
        query = {}
        if tenant_id is not None:
            query["tenant_id"] = tenant_id
        if user_id:
            query["user_id"] = str(user_id)
        logs = ActivityLog.collection.find(query).sort("timestamp", -1).limit(limit)
        return list(logs)

    @staticmethod
    def to_dict(entry):
        return {
            "id": str(entry.get("_id")) if entry.get("_id") else None,
            "tenant_id": str(entry.get("tenant_id")) if entry.get("tenant_id") else None,
            "user_id": str(entry.get("user_id")) if entry.get("user_id") else None,
            "action": entry.get("action"),
            "category": entry.get("category"),
            "server_id": str(entry.get("server_id")) if entry.get("server_id") else None,
            "session_id": str(entry.get("session_id")) if entry.get("session_id") else None,
            "ip_address": entry.get("ip_address"),
            "success": bool(entry.get("success")),
            "reason": entry.get("reason"),
            "actor_role": entry.get("actor_role"),
            "metadata": _json_safe(entry.get("metadata") or {}),
            "created_at": entry.get("created_at").isoformat() if entry.get("created_at") else None,
        }
