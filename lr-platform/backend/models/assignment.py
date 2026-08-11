from datetime import datetime
from bson import ObjectId
from backend.extensions import db
from backend.models.application import PublishedApp
from backend.tenancy.context import scoped_filter, tenant_document


def _object_id(value):
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return None
    

class ApplicationAssignment:

    collection = db["application_assignments"]
    apps_collection = db["published_apps"]

    @staticmethod
    def assign(user_id, app_id, is_default=False, tenant_id=None):
        user_id = _object_id(user_id)
        app_id = _object_id(app_id)
        if not user_id or not app_id:
            return None

        query = {
            "user_id": user_id,
            "app_id": app_id
        }
        existing = ApplicationAssignment.collection.find_one(scoped_filter(tenant_id, query) if tenant_id is not None else query)

        if existing:
            return None

        assignment = {
            "user_id": user_id,
            "app_id": app_id,
            "is_enabled": True,
            "is_default": bool(is_default),
            "assigned_at": datetime.utcnow()
        }
        if tenant_id is not None:
            assignment = tenant_document(tenant_id, assignment)

        result = ApplicationAssignment.collection.insert_one(assignment)
        assignment["_id"] = result.inserted_id
        return assignment

    @staticmethod
    def find(user_id, app_id, tenant_id=None):
        user_oid = _object_id(user_id)
        app_oid = _object_id(app_id)
        if not user_oid or not app_oid:
            return None
        user_ids = [user_oid, str(user_id)]
        app_ids = [app_oid, str(app_id)]
        query = {
            "user_id": {"$in": user_ids},
            "app_id": {"$in": app_ids}
        }
        return ApplicationAssignment.collection.find_one(scoped_filter(tenant_id, query) if tenant_id is not None else query)

    @staticmethod
    def defaults_for_user(user_id, tenant_id=None):
        return [
            assignment
            for assignment in ApplicationAssignment.for_user(user_id, tenant_id)
            if assignment.get("is_default") is True
        ]

    @staticmethod
    def for_user(user_id, tenant_id=None):
        user_oid = _object_id(user_id)
        user_ids = [str(user_id)]
        if user_oid:
            user_ids.append(user_oid)
        query = {
            "user_id": {"$in": user_ids},
            "is_enabled": True,
        }
        return list(ApplicationAssignment.collection.find(scoped_filter(tenant_id, query) if tenant_id is not None else query))

    @staticmethod
    def set_default(user_id, app_id):
        user_oid = _object_id(user_id)
        app_oid = _object_id(app_id)
        if not user_oid or not app_oid:
            return None
        user_ids = [user_oid, str(user_id)]
        ApplicationAssignment.collection.update_many(
            {"user_id": {"$in": user_ids}},
            {"$set": {"is_default": False}},
        )
        return ApplicationAssignment.collection.update_one(
            {
                "user_id": {"$in": user_ids},
                "app_id": {"$in": [app_oid, str(app_id)]},
                "is_enabled": True,
            },
            {"$set": {"is_default": True}},
        )

    @staticmethod
    def to_dict(assignment):

        app = ApplicationAssignment.apps_collection.find_one({
            "_id": assignment.get("app_id")
        })

        return {
            "id": str(assignment.get("_id")),
            "user_id": str(assignment.get("user_id")) if assignment.get("user_id") else None,
            "app_id": str(assignment.get("app_id")) if assignment.get("app_id") else None,
            "is_enabled": assignment.get("is_enabled"),
            "is_default": bool(assignment.get("is_default")),
            "assigned_at": assignment.get("assigned_at").isoformat() if assignment.get("assigned_at") else None,
            "app": PublishedApp.to_dict(app) if app else None,
        }
