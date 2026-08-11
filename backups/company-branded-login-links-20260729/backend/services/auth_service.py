from datetime import datetime

import re
from flask_login import login_user, logout_user

from backend.models.login_link import LoginLink
from backend.models.server import Server
from backend.models.tenant import Tenant
from backend.models.user import User
from backend.security.credential_crypto import encrypt_secret
from backend.services.windows_account_service import WindowsAccountService
from shared.security.password import hash_password, verify_password


def _clean_text(value):
    return str(value or "").strip()


def _user_response(user):
    return User.to_dict(user) if user else None


def _password_matches(password, stored_password):
    if not password or not stored_password:
        return False

    try:
        if verify_password(password, stored_password):
            return True
    except Exception:
        pass

    return password == stored_password


def _normalize_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"false", "0", "no", "off"}


def _sync_windows_credentials_from_login(user, username, password):
    if not user or not username or not password:
        return

    windows_username = _clean_text(user.get("windows_username"))
    if windows_username and windows_username.lower() != username.lower():
        return
    if user.get("windows_password"):
        return

    updates = {
        "windows_username": windows_username or username,
        "windows_password": encrypt_secret(password),
        "windows_account_enabled": True,
    }
    if "windows_domain" not in user:
        updates["windows_domain"] = None

    User.update(user.id, updates)
    user.update(updates)


def _windows_account_updates(data, existing_user=None):
    updates = {}

    for source_key, target_key in (
        ("windows_username", "windows_username"),
        ("rdp_username", "windows_username"),
        ("windows_domain", "windows_domain"),
        ("rdp_domain", "windows_domain"),
    ):
        if source_key in data:
            updates[target_key] = _clean_text(data.get(source_key)) or None

    if "windows_account_scope" in data:
        scope = _clean_text(data.get("windows_account_scope")).lower()
        updates["windows_account_scope"] = scope if scope in {"local", "domain"} else None
        if scope == "local":
            updates["windows_domain"] = None

    password_value = None
    password_provided = False
    for key in ("windows_password", "rdp_password"):
        if key in data:
            password_value = data.get(key)
            password_provided = True
            break
    if password_provided:
        updates["windows_password"] = encrypt_secret(password_value)

    if "windows_account_enabled" in data:
        updates["windows_account_enabled"] = _normalize_bool(data.get("windows_account_enabled"), False)
    elif "rdp_enabled" in data:
        updates["windows_account_enabled"] = _normalize_bool(data.get("rdp_enabled"), False)
    elif existing_user is None and updates.get("windows_username"):
        updates["windows_account_enabled"] = True

    if updates.get("windows_username") is None and "windows_username" in updates:
        updates["windows_account_enabled"] = False
        updates["windows_password"] = None
        updates["windows_domain"] = None
        updates["windows_account_scope"] = None

    return updates


class AuthService:

    @staticmethod
    def register_user(username, password):
        username = _clean_text(username)
        password = str(password or "")

        if not username or not password:
            return None, "Username and password are required"

        if User.username_exists(username):
            return None, "Username already exists"

        user = User.create(username, hash_password(password), "User")
        if not user:
            return None, "Username already exists"

        return user, None

    @staticmethod
    def login(username, password, token=None, inactive_status=401, company=None):
        username = _clean_text(username)
        password = str(password or "")
        company = _clean_text(company)

        company_separator = chr(92)
        if not company and company_separator in username:
            company, username = username.split(company_separator, 1)
            company = _clean_text(company)
            username = _clean_text(username)

        if not username or not password:
            return None, "Username and password are required", 400

        tenant = Tenant.get_by_code(company) if company else None
        if company and not tenant:
            return None, "Invalid company code, username or password", 401

        if tenant:
            user = User.find_by_username(username, tenant.get("_id"))
        else:
            candidates = User.find_all_by_username(username, limit=2)
            if len(candidates) > 1:
                return None, "Company code is required for this username", 400
            user = candidates[0] if candidates else None
        if not user or not _password_matches(password, user.get("password")):
            return None, "Invalid username or password", 401

        if not user.is_active:
            return None, "User is disabled", inactive_status

        if user.get("tenant_id"):
            user_tenant = tenant or Tenant.get_by_id(user.get("tenant_id"))
            if not user_tenant or not user_tenant.get("is_active") or user_tenant.get("registration_status") != "active":
                return None, "Company account is inactive", 423

        if user.two_factor_enabled and not _clean_text(token):
            return None, "Two-factor code is required", 401

        # 2FA verification is not configured yet; keep the response explicit.
        if user.two_factor_enabled:
            return None, "Two-factor verification is not configured", 501

        _sync_windows_credentials_from_login(user, username, password)
        login_user(user)
        User.update_login(user.id, tenant_id=user.get("tenant_id"))
        return user, "Login successful", 200

    @staticmethod
    def login_via_link(token):
        token = _clean_text(token)
        link = LoginLink.get_by_token(token)
        if link is None or not LoginLink.is_valid(link):
            return None, "Invalid login link", 403

        user_id = link.get("user_id")
        if not user_id:
            return None, "Login link is not assigned to a user", 403

        user = User.get_by_id(user_id, tenant_id=link.get("tenant_id"))
        if not user or not user.is_active:
            return None, "User is disabled or not found", 403

        login_user(user)
        User.update_login(user.id)
        if link.get("one_time"):
            LoginLink.mark_used(token)

        return user, None, 200

    @staticmethod
    def logout():
        logout_user()
        return True

    @staticmethod
    def me(user):
        return {
            "success": True,
            "user": _user_response(user),
        }, 200

    @staticmethod
    def list_users(params, actor=None):
        params = params or {}
        try:
            limit = min(max(int(params.get("limit", 500)), 1), 1000)
        except (TypeError, ValueError):
            limit = 500
        try:
            offset = max(int(params.get("offset", 0)), 0)
        except (TypeError, ValueError):
            offset = 0

        query = {}
        tenant_id = actor.get("tenant_id") if actor else None
        if tenant_id:
            query["tenant_id"] = tenant_id
        search = _clean_text(params.get("q") or params.get("search"))
        if search:
            query["username"] = {"$regex": re.escape(search), "$options": "i"}
        role = _clean_text(params.get("role"))
        if role:
            query["role"] = role

        cursor = User.collection.find(query).sort("username", 1).skip(offset).limit(limit)
        users = [User.to_dict(user) for user in cursor]
        total = User.collection.count_documents(query)
        return {
            "success": True,
            "users": users,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(users) < total,
        }, 200

    @staticmethod
    def create_user(data, actor_id, ip_address):
        username = _clean_text(data.get("username"))
        password = str(data.get("password") or "")
        role = data.get("role") or data.get("role_name") or "User"
        email = _clean_text(data.get("email"))

        if not username or not password:
            return {"message": "Username and password are required"}, 400

        actor = User.get_by_id(actor_id) if actor_id else None
        tenant_id = actor.get("tenant_id") if actor else None
        if actor_id and not tenant_id:
            return {"message": "Admin tenant migration is required"}, 423
        if User.username_exists(username, tenant_id):
            return {"message": "Username already exists"}, 409

        windows_enabled = WindowsAccountService.normalize_bool(
            data.get("windows_account_enabled"),
            True,
        )
        create_windows_account = WindowsAccountService.normalize_bool(
            data.get("windows_create_account"),
            True,
        )
        target_server = None
        target_server_id = _clean_text(
            data.get("windows_server_id") or data.get("server_id")
        )
        if windows_enabled:
            if not target_server_id:
                return {
                    "message": "Select the Windows server where this user account must be created"
                }, 400
            target_server = Server.get_by_id(target_server_id, tenant_id)
            if not target_server or target_server.get("is_active") is False:
                return {"message": "Selected Windows server is not available for this company"}, 404

        provisioning_data = dict(data)
        provisioning_data["_tenant_id"] = tenant_id
        if target_server:
            provisioning_data["server_id"] = target_server.get("_id")
            provisioning_data["windows_server_id"] = target_server.get("_id")
            provisioning_data["agent_id"] = target_server.get("agent_id")
            provisioning_data["windows_agent_id"] = target_server.get("agent_id")
        windows_updates, windows_error = WindowsAccountService.build_updates(
            provisioning_data,
            default_username=username,
            default_password=password,
            create_local_account=create_windows_account,
        )
        if windows_error:
            return {"message": windows_error}, 400

        try:
            user = User.create(username, hash_password(password), role, tenant_id=tenant_id, email=email or None)
        except ValueError as error:
            return {"message": str(error)}, 400
        if not user:
            return {"message": "Username already exists"}, 409

        user_id = user.id

        updates = {
            "created_at": datetime.utcnow(),
            "created_by": actor_id,
        }
        if email:
            updates["email"] = email
        updates.update(windows_updates or {})
        if target_server:
            updates["windows_server_id"] = target_server.get("_id")
            updates["windows_agent_id"] = target_server.get("agent_id")

        if updates:
            User.update(user_id, updates, tenant_id=tenant_id)
            user = User.get_by_id(user_id, tenant_id=tenant_id)

        return {
            "success": True,
            "message": (
                "Windows user and LR login created successfully"
                if windows_enabled and create_windows_account
                else "User created successfully"
            ),
            "server": Server.to_dict(target_server) if target_server else None,
            "user": _user_response(user),
        }, 201

    @staticmethod
    def update_user(user_id, data, actor_id, ip_address):
        actor = User.get_by_id(actor_id) if actor_id else None
        tenant_id = actor.get("tenant_id") if actor else None
        if actor_id and not tenant_id:
            return {"message": "Admin tenant migration is required"}, 423
        user = User.get_by_id(user_id, tenant_id=tenant_id)
        if not user:
            return {"message": "User not found"}, 404

        updates = {
            "updated_at": datetime.utcnow(),
            "updated_by": actor_id,
        }

        username = _clean_text(data.get("username"))
        if username and username != user.username:
            existing = User.find_by_username(username, tenant_id)
            if existing and existing.id != user.id:
                return {"message": "Username already exists"}, 409
            updates["username"] = username

        email = _clean_text(data.get("email"))
        if email:
            updates["email"] = email

        password = data.get("password")
        if password:
            updates["password"] = hash_password(str(password))

        role = data.get("role") or data.get("role_name")
        if role:
            try:
                updates["role"] = User.normalize_role(role)
            except ValueError as error:
                return {"message": str(error)}, 400

        if "is_active" in data:
            updates["is_active"] = _normalize_bool(data.get("is_active"))

        if "default_application_id" in data:
            updates["default_application_id"] = _clean_text(data.get("default_application_id")) or None

        updates.update(_windows_account_updates(data, user))

        User.update(user_id, updates, tenant_id=tenant_id)
        updated_user = User.get_by_id(user_id, tenant_id=tenant_id)

        return {
            "success": True,
            "message": "User updated successfully",
            "user": _user_response(updated_user),
        }, 200


class UserService:

    @staticmethod
    def delete_user(user_id, actor_id, ip_address):
        actor = User.get_by_id(actor_id) if actor_id else None
        tenant_id = actor.get("tenant_id") if actor else None
        if actor_id and not tenant_id:
            return {"message": "Admin tenant migration is required"}, 423
        result = User.delete(user_id, tenant_id=tenant_id)
        if result.deleted_count == 0:
            return {"message": "User not found"}, 404

        return {
            "success": True,
            "message": "User deleted successfully"
        }, 200

    @staticmethod
    def bulk_delete(user_ids, actor_id, ip_address):
        actor = User.get_by_id(actor_id) if actor_id else None
        tenant_id = actor.get("tenant_id") if actor else None
        if actor_id and not tenant_id:
            return {"message": "Admin tenant migration is required"}, 423
        deleted = 0
        for user_id in user_ids or []:
            result = User.delete(user_id, tenant_id=tenant_id)
            deleted += result.deleted_count

        return {
            "success": True,
            "message": "Users deleted successfully",
            "deleted": deleted
        }, 200

    @staticmethod
    def import_csv(rows, actor_id, ip_address):
        created = 0
        skipped_rows = []

        for index, row in enumerate(rows or [], start=1):
            username = _clean_text(row.get("username"))
            password = str(row.get("password") or "")
            role = row.get("role") or row.get("role_name") or "User"

            if not username or not password:
                skipped_rows.append({"row": index, "message": "Username and password are required"})
                continue

            response, code = AuthService.create_user(row, actor_id, ip_address)
            if code == 201:
                created += 1
            else:
                skipped_rows.append({"row": index, "message": response.get("message", "Skipped")})

        return {
            "success": True,
            "message": "CSV import completed",
            "created": created,
            "skipped_rows": skipped_rows
        }, 200

    @staticmethod
    def update_role(user_id, role_data, actor_id, ip_address):
        return AuthService.update_user(
            user_id,
            {"role": role_data.get("role") or role_data.get("role_name")},
            actor_id,
            ip_address
        )
