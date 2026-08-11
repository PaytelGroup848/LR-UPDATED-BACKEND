from datetime import datetime
from bson import ObjectId
from backend.extensions import db


def _object_id(value):
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return None


class LoginLink:

    collection = db["login_links"]
    users_collection = db["users"]  # relation ke liye

    @staticmethod
    def create(token, user_id=None, expires_at=None, one_time=True, created_by=None, tenant_id=None):

        link = {
            "tenant_id": tenant_id,
            "token": token,
            "user_id": user_id,
            "expires_at": expires_at,
            "one_time": one_time,
            "revoked_at": None,
            "used_at": None,
            "created_by": created_by,
            "created_at": datetime.utcnow()
        }

        # unique token check
        existing = LoginLink.collection.find_one({"token": token})
        if existing:
            return None

        result = LoginLink.collection.insert_one(link)
        link["_id"] = result.inserted_id
        return link

    @staticmethod
    def get_by_token(token):
        return LoginLink.collection.find_one({"token": token})

    @staticmethod
    def mark_used(token):
        return LoginLink.collection.update_one(
            {"token": token},
            {"$set": {"used_at": datetime.utcnow()}}
        )

    @staticmethod
    def revoke(token):
        return LoginLink.collection.update_one(
            {"token": token},
            {"$set": {"revoked_at": datetime.utcnow()}}
        )

    @staticmethod
    def is_valid(link):
        now = datetime.utcnow()

        if not link:
            return False
        if link.get("revoked_at"):
            return False
        if link.get("expires_at") and link["expires_at"] <= now:
            return False
        if link.get("one_time") and link.get("used_at"):
            return False

        return True

    @staticmethod
    def to_dict(link):
        user = None

        if link.get("user_id"):
            user_id = _object_id(link["user_id"])
            user_query = {"_id": user_id or link["user_id"]}
            if link.get("tenant_id"):
                user_query["tenant_id"] = link["tenant_id"]
            user = LoginLink.users_collection.find_one(user_query)

        return {
            "id": str(link.get("_id")),
            "tenant_id": str(link.get("tenant_id")) if link.get("tenant_id") else None,
            "token": link.get("token"),
            "user_id": str(link.get("user_id")) if link.get("user_id") else None,
            "username": user.get("username") if user else None,
            "expires_at": link.get("expires_at").isoformat() if link.get("expires_at") else None,
            "one_time": bool(link.get("one_time")),
            "revoked_at": link.get("revoked_at").isoformat() if link.get("revoked_at") else None,
            "used_at": link.get("used_at").isoformat() if link.get("used_at") else None,
            "created_by": str(link.get("created_by")) if link.get("created_by") else None,
            "created_at": link.get("created_at").isoformat() if link.get("created_at") else None,
            "is_valid": LoginLink.is_valid(link),
        }
