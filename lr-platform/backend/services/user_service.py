from shared.security.password import hash_password
from backend.security.credential_crypto import encrypt_secret
from backend.models.user import User
from backend.services.windows_account_service import WindowsAccountService
from backend.services.user_desktop_service import UserDesktopService


class UserService:

    def __init__(self, user_repository, role_repository):
        self.user_repository = user_repository
        self.role_repository = role_repository

    def create_user(
        self,
        username,
        email,
        password,
        role_name,
        windows_username=None,
        windows_password=None,
        windows_domain=None,
        windows_account_scope=None,
        windows_account_enabled=False,
        windows_create_account=False,
        windows_server_id=None,
        windows_agent_id=None,
        tenant_id=None,
    ):
        if self.user_repository.exists_by_username(username):
            raise ValueError("Username already exists")

        if self.user_repository.exists_by_email(email):
            raise ValueError("Email already exists")

        role = self.role_repository.get_by_name(role_name)
        if not role:
            raise ValueError("Role not found")
        if windows_account_enabled and not windows_server_id:
            raise ValueError("Select the Windows server where this user account must be created")

        windows_updates, windows_error = WindowsAccountService.build_updates(
            {
                "windows_username": windows_username,
                "windows_password": windows_password,
                "windows_domain": windows_domain,
                "windows_account_scope": windows_account_scope,
                "windows_account_enabled": windows_account_enabled,
                "windows_server_id": windows_server_id,
                "windows_agent_id": windows_agent_id,
                "_tenant_id": tenant_id,
            },
            default_username=username,
            default_password=password,
            create_local_account=windows_create_account,
        )
        if windows_error:
            raise ValueError(windows_error)
        if windows_account_enabled:
            windows_updates["windows_server_id"] = windows_server_id
            windows_updates["windows_agent_id"] = windows_agent_id

        user = {
            "username": username,
            "email": email,
            "password": hash_password(password),
            "role": User.normalize_role(role.name),
            "role_id": role.id,
            "is_active": True,
        }
        user.update(windows_updates or {})

        created_user = self.user_repository.create(user)
        try:
            UserDesktopService.register_user_desktop(created_user)
        except Exception:
            pass
        return created_user

    def update_user(self, user_id, data):
        user = self.user_repository.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        updates = {}
        if "email" in data and data.get("email"):
            updates["email"] = str(data.get("email")).strip()
        if data.get("password"):
            updates["password"] = hash_password(str(data.get("password")))
        if "is_active" in data and data.get("is_active") is not None:
            updates["is_active"] = bool(data.get("is_active"))

        role_name = data.get("role_name")
        if role_name:
            role = self.role_repository.get_by_name(role_name)
            if not role:
                raise ValueError("Role not found")
            updates["role"] = User.normalize_role(role.name)
            updates["role_id"] = role.id

        if "windows_account_enabled" in data and data.get("windows_account_enabled") is not None:
            enabled = bool(data.get("windows_account_enabled"))
            updates["windows_account_enabled"] = enabled
            if not enabled:
                updates.update({
                    "windows_username": None,
                    "windows_domain": None,
                    "windows_account_scope": None,
                    "windows_password": None,
                })

        if "windows_username" in data:
            username = str(data.get("windows_username") or "").strip()
            updates["windows_username"] = username or None
        if "windows_domain" in data:
            domain = str(data.get("windows_domain") or "").strip()
            updates["windows_domain"] = domain or None
        if "windows_account_scope" in data:
            scope = str(data.get("windows_account_scope") or "").strip().lower()
            if scope not in {"local", "domain"}:
                raise ValueError("Windows account scope must be local or domain")
            updates["windows_account_scope"] = scope
            if scope == "local":
                updates["windows_domain"] = None
        if data.get("windows_password"):
            updates["windows_password"] = encrypt_secret(str(data.get("windows_password")))

        enabled = updates.get(
            "windows_account_enabled",
            bool(user.get("windows_account_enabled")),
        )
        username = updates.get("windows_username", user.get("windows_username"))
        password = updates.get("windows_password", user.get("windows_password"))
        if enabled and (not username or not password):
            raise ValueError("Windows username and password are required when the Windows account is enabled")

        document = dict(user)
        document.update(updates)
        return self.user_repository.update(document)
