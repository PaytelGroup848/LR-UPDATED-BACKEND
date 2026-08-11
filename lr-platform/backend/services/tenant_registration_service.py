from datetime import datetime
import re
import uuid

from pymongo.errors import DuplicateKeyError

from backend.core.config import settings
from backend.models.tenant import (
    Tenant,
    is_valid_company_code,
    normalize_company_code,
    slugify_company,
)
from backend.models.user import User
from backend.services.registration_rate_limit_service import RegistrationRateLimitService
from shared.security.password import hash_password


class TenantRegistrationError(ValueError):
    def __init__(self, message, status_code=400, code="invalid_registration"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class TenantRegistrationService:
    @staticmethod
    def _clean(value):
        return str(value or "").strip()

    @classmethod
    def register(cls, data, remote_address=None, user_agent=None):
        if not settings.TENANT_REGISTRATION_ENABLED:
            raise TenantRegistrationError("Company registration is disabled", 403, "registration_disabled")
        if not RegistrationRateLimitService.check_and_record(remote_address):
            raise TenantRegistrationError("Too many registration attempts", 429, "rate_limited")

        company_name = cls._clean(data.get("company_name"))
        company_code = normalize_company_code(data.get("company_code"))
        email = cls._clean(data.get("admin_email") or data.get("email")).lower()
        password = str(data.get("admin_password") or data.get("password") or "")
        confirm_password = str(data.get("confirm_password") or "")
        username = email
        slug = slugify_company(company_name)

        if len(company_name) < 2 or not slug:
            raise TenantRegistrationError("Valid company_name is required")
        if not is_valid_company_code(company_code):
            raise TenantRegistrationError(
                "Company code must be 3-32 characters using letters, numbers, hyphen or underscore"
            )
        if "@" not in email or len(email) > 254:
            raise TenantRegistrationError("Valid email is required")
        if not re.fullmatch(r"[A-Za-z0-9_.@+-]{3,254}", username):
            raise TenantRegistrationError("Valid email is required")
        if len(password) < 8:
            raise TenantRegistrationError("Password must be at least 8 characters")
        if not confirm_password:
            raise TenantRegistrationError("Confirm password is required")
        if password != confirm_password:
            raise TenantRegistrationError("Password and confirm password do not match")
        if Tenant.get_by_code(company_code):
            raise TenantRegistrationError("Company code already exists", 409, "company_code_exists")
        if Tenant.collection.find_one({"company_slug": slug}):
            raise TenantRegistrationError("Company name already exists", 409, "company_exists")
        registration_id = uuid.uuid4().hex
        tenant = Tenant.create_pending(company_name, company_code, registration_id, {
            "registration_ip": remote_address,
            "user_agent": str(user_agent or "")[:500],
        })
        user = None
        try:
            user = User.create(
                username,
                hash_password(password),
                "Admin",
                tenant_id=tenant["_id"],
                email=email,
            )
            if not user:
                raise TenantRegistrationError("Username already exists", 409, "admin_exists")

            now = datetime.utcnow()
            result = Tenant.collection.update_one(
                {"_id": tenant["_id"], "registration_id": registration_id, "registration_status": "pending"},
                {"$set": {
                    "admin_user_id": user.get("_id"),
                    "registration_status": "active",
                    "is_active": True,
                    "updated_at": now,
                }},
            )
            if result.modified_count != 1:
                raise RuntimeError("Tenant registration could not be finalized")
            tenant = Tenant.get_by_id(tenant["_id"])
            return {
                "success": True,
                "message": "Company registered successfully",
                "tenant": Tenant.to_dict(tenant),
                "admin": User.to_dict(user),
            }
        except TenantRegistrationError:
            cls._rollback(tenant, user, registration_id)
            raise
        except DuplicateKeyError as error:
            cls._rollback(tenant, user, registration_id)
            raise TenantRegistrationError(
                "Company code already exists", 409, "company_code_exists"
            ) from error
        except Exception:
            cls._rollback(tenant, user, registration_id)
            raise

    @staticmethod
    def _rollback(tenant, user, registration_id):
        tenant_id = tenant.get("_id") if tenant else None
        if user and tenant_id:
            User.collection.delete_one({"_id": user.get("_id"), "tenant_id": tenant_id})
        if tenant_id:
            Tenant.collection.delete_one({
                "_id": tenant_id,
                "registration_id": registration_id,
                "registration_status": "pending",
            })
