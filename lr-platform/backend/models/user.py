from datetime import datetime
from backend.extensions import db


class MongoUser(dict):
    @property
    def id(self):
        return str(self.get("_id"))

    @property
    def username(self):
        return self.get("username")

    @username.setter
    def username(self, value):
        self["username"] = value

    @property
    def password(self):
        return self.get("password")

    @password.setter
    def password(self, value):
        self["password"] = value

    @property
    def email(self):
        return self.get("email")

    @email.setter
    def email(self, value):
        self["email"] = value

    @property
    def role(self):
        return self.get("role")

    @property
    def role_id(self):
        return self.get("role_id")

    @property
    def tenant_id(self):
        value = self.get("tenant_id")
        return str(value) if value is not None else None

    @property
    def is_active(self):
        return bool(self.get("is_active"))

    @is_active.setter
    def is_active(self, value):
        self["is_active"] = bool(value)

    @property
    def two_factor_enabled(self):
        return bool(self.get("two_factor_enabled"))

    @property
    def two_factor_secret(self):
        return self.get("two_factor_secret")

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.get("_id"))

    def has_role(self, *roles):
        return User.has_role(self, *roles)

    def to_dict(self):
        return User.to_dict(self)

    def set_role(self, role):
        self["role"] = User.normalize_role(role)
        User.update(self.id, {"role": self["role"]})


class User:

    collection = db["users"]

    @staticmethod
    def _wrap(user):
        return MongoUser(user) if user else None

    ROLES = ("Admin", "User")

    @classmethod
    def _role_key(cls, role):
        return str(role or "").strip().upper().replace("-", "_").replace(" ", "_")

    # ✅ CREATE USER
    @staticmethod
    def create(username, password, role="User", tenant_id=None, email=None):

        role = User.normalize_role(role)

        query = {"username": username}
        tenant_object_id = None
        if tenant_id is not None:
            from backend.tenancy.context import as_object_id
            tenant_object_id = as_object_id(tenant_id)
            query["tenant_id"] = tenant_object_id
        else:
            query["$or"] = [
                {"tenant_id": {"$exists": False}},
                {"tenant_id": None},
            ]

        # Usernames are unique inside a company, not across all companies.
        if User.collection.find_one(query):
            return None

        user = {
            "username": username,
            "email": email,
            "password": password,
            "role": role,
            "is_active": True,
            "created_at": datetime.utcnow(),
            "last_login_at": None,
            "two_factor_enabled": False,
            "two_factor_secret": None,
            "assigned_app": None,
            "default_application_id": None,
            "windows_username": None,
            "windows_domain": None,
            "windows_account_scope": None,
            "windows_password": None,
            "windows_account_enabled": False,
            "windows_server_id": None,
            "windows_agent_id": None,
            "windows_account_provisioned": False,
            "windows_account_provisioned_at": None,
        }

        if tenant_object_id is not None:
            user["tenant_id"] = tenant_object_id

        result = User.collection.insert_one(user)
        user["_id"] = result.inserted_id
        return User._wrap(user)

    # ✅ ROLE NORMALIZATION
    @classmethod
    def normalize_role(cls, role):
        value = (role or 'User').strip().title()
        if value not in cls.ROLES:
            raise ValueError(f'Invalid role. Allowed roles: {", ".join(cls.ROLES)}')
        return value

    # ✅ ROLE CHECK
    @staticmethod
    def has_role(user, *roles):
        current_role = User._role_key(user.get("role"))
        required_roles = {User._role_key(role) for role in roles}
        return current_role in required_roles

    # ✅ FLAGS
    @staticmethod
    def is_admin(user):
        return User._role_key(user.get("role")) == "ADMIN"

    # ✅ UPDATE LAST LOGIN
    @staticmethod
    def update_login(user_id, tenant_id=None):
        from bson import ObjectId
        query = {"_id": ObjectId(user_id)}
        if tenant_id is not None:
            from backend.tenancy.context import scoped_filter
            query = scoped_filter(tenant_id, query)
        return User.collection.update_one(
            query,
            {"$set": {"last_login_at": datetime.utcnow()}}
        )

    # ✅ FIND USER
    @staticmethod
    def get_by_id(user_id, tenant_id=None):
        from bson import ObjectId
        try:
            query = {"_id": ObjectId(user_id)}
            if tenant_id is not None:
                from backend.tenancy.context import scoped_filter
                query = scoped_filter(tenant_id, query)
            return User._wrap(User.collection.find_one(query))
        except:
            return None

    @staticmethod
    def find_by_username(username, tenant_id=None):
        if not username:
            return None
        query = {"username": username}
        if tenant_id is not None:
            from backend.tenancy.context import scoped_filter
            query = scoped_filter(tenant_id, query)
        return User._wrap(User.collection.find_one(query))

    @staticmethod
    def find_all_by_username(username, limit=2):
        if not username:
            return []
        cursor = User.collection.find({"username": username}).limit(max(int(limit), 1))
        return [User._wrap(user) for user in cursor]

    @staticmethod
    def username_exists(username, tenant_id=None):
        return User.find_by_username(username, tenant_id) is not None

    # ✅ UPDATE USER
    @staticmethod
    def update(user_id, data, tenant_id=None):
        from bson import ObjectId

        if "role" in data:
            data["role"] = User.normalize_role(data["role"])

        query = {"_id": ObjectId(user_id)}
        if tenant_id is not None:
            from backend.tenancy.context import scoped_filter
            query = scoped_filter(tenant_id, query)
        data.pop("tenant_id", None)
        return User.collection.update_one(
            query,
            {"$set": data}
        )

    # ✅ DELETE USER
    @staticmethod
    def delete(user_id, tenant_id=None):
        from bson import ObjectId
        query = {"_id": ObjectId(user_id)}
        if tenant_id is not None:
            from backend.tenancy.context import scoped_filter
            query = scoped_filter(tenant_id, query)
        return User.collection.delete_one(query)

    # ✅ AUTH COMPATIBILITY (Flask-Login type)
    @staticmethod
    def get_id(user):
        return str(user.get("_id"))

    @staticmethod
    def is_authenticated(user):
        return True

    @staticmethod
    def is_anonymous(user):
        return False

    # ✅ TO DICT
    @staticmethod
    def to_dict(user):
        windows_username = user.get("windows_username")
        return {
            "id": str(user.get("_id")),
            "tenant_id": str(user.get("tenant_id")) if user.get("tenant_id") else None,
            "username": user.get("username"),
            "email": user.get("email"),
            "role": user.get("role"),
            "role_id": user.get("role_id"),
            "is_active": bool(user.get("is_active")),
            "created_at": user.get("created_at").isoformat() if user.get("created_at") else None,
            "last_login_at": user.get("last_login_at").isoformat() if user.get("last_login_at") else None,
            "two_factor_enabled": bool(user.get("two_factor_enabled")),
            "windows_username": windows_username,
            "windows_domain": user.get("windows_domain"),
            "windows_account_scope": user.get("windows_account_scope"),
            "windows_account_enabled": bool(user.get("windows_account_enabled") and windows_username),
            "windows_account_configured": bool(windows_username and user.get("windows_password")),
            "windows_server_id": str(user.get("windows_server_id")) if user.get("windows_server_id") else None,
            "windows_agent_id": user.get("windows_agent_id"),
            "windows_account_provisioned": bool(user.get("windows_account_provisioned")),
            "windows_account_provisioned_at": (
                user.get("windows_account_provisioned_at").isoformat()
                if user.get("windows_account_provisioned_at")
                else None
            ),
        }
