from datetime import datetime

from bson import ObjectId

from backend.models.role import Role
from backend.models.user import User
from backend.tenancy.context import as_object_id, scoped_filter


class UserRepository:
    def __init__(self, db, tenant_id=None):
        self.collection = db["users"]
        self.tenant_id = as_object_id(tenant_id) if tenant_id is not None else None

    def _wrap(self, user):
        return User._wrap(user)

    def _id_filter(self, user_id):
        if isinstance(user_id, ObjectId):
            query = {"_id": user_id}
            return scoped_filter(self.tenant_id, query) if self.tenant_id else query
        try:
            query = {"_id": ObjectId(str(user_id))}
            return scoped_filter(self.tenant_id, query) if self.tenant_id else query
        except Exception:
            query = {"id": user_id}
            return scoped_filter(self.tenant_id, query) if self.tenant_id else query

    def _scope(self, query=None):
        return scoped_filter(self.tenant_id, query) if self.tenant_id else dict(query or {})

    def get_by_id(self, user_id):
        return self._wrap(self.collection.find_one(self._id_filter(user_id)))

    def get_by_username(self, username: str):
        return self._wrap(self.collection.find_one(self._scope({"username": username})))

    def get_by_email(self, email: str):
        return self._wrap(self.collection.find_one(self._scope({"email": email})))

    def exists_by_username(self, username: str) -> bool:
        return self.collection.find_one(self._scope({"username": username})) is not None

    def exists_by_email(self, email: str) -> bool:
        return self.collection.find_one(self._scope({"email": email})) is not None

    def create(self, user):
        document = dict(user)
        if self.tenant_id:
            supplied_tenant = document.pop("tenant_id", None)
            if supplied_tenant is not None and as_object_id(supplied_tenant) != self.tenant_id:
                raise ValueError("Cross-tenant user create rejected")
            document["tenant_id"] = self.tenant_id
        role_name = document.get("role") or document.get("role_name") or "USER"
        role = Role.get_by_name(role_name)
        if not role:
            raise ValueError("Role not found. Allowed roles: Admin, User")
        document["role"] = User.normalize_role(role.name)
        document["role_id"] = role.id
        document.setdefault("is_active", True)
        document.setdefault("created_at", datetime.utcnow())
        result = self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return self._wrap(document)

    def update(self, user):
        updates = dict(user)
        user_id = updates.pop("_id", None) or updates.pop("id", None)
        if not user_id:
            return user
        updates.pop("tenant_id", None)
        self.collection.update_one(self._id_filter(user_id), {"$set": updates})
        return self.get_by_id(user_id)

    def delete(self, user) -> None:
        user_id = user.get("_id") if isinstance(user, dict) else getattr(user, "id", None)
        if user_id:
            self.collection.delete_one(self._id_filter(user_id))

    def get_all(self):
        return [self._wrap(item) for item in self.collection.find(self._scope()).sort("username", 1)]
