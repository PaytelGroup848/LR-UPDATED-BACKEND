from datetime import datetime
import re

from bson import ObjectId

from backend.extensions import db


def slugify_company(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug[:80]


def normalize_company_code(value: str) -> str:
    return str(value or "").strip().lower()


def is_valid_company_code(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,31}", normalize_company_code(value)))


class Tenant:
    collection = db["tenants"]

    @staticmethod
    def get_by_id(tenant_id):
        try:
            object_id = tenant_id if isinstance(tenant_id, ObjectId) else ObjectId(str(tenant_id))
        except Exception:
            return None
        return Tenant.collection.find_one({"_id": object_id})

    @staticmethod
    def get_by_slug(slug):
        return Tenant.collection.find_one({"company_slug": slugify_company(slug)})

    @staticmethod
    def get_by_code(company_code):
        code = normalize_company_code(company_code)
        if not code:
            return None
        tenant = Tenant.collection.find_one({"company_code": code})
        if tenant:
            return tenant
        # Compatibility for tenants created before company_code was stored.
        return Tenant.collection.find_one({
            "company_code": {"$in": [None, ""]},
            "company_slug": slugify_company(code),
        })

    @staticmethod
    def to_dict(tenant, *, include_internal=False):
        if not tenant:
            return None
        result = {
            "id": str(tenant.get("_id")),
            "company_name": tenant.get("company_name"),
            "company_code": tenant.get("company_code") or tenant.get("company_slug"),
            "company_slug": tenant.get("company_slug"),
            "admin_user_id": str(tenant.get("admin_user_id")) if tenant.get("admin_user_id") else None,
            "registration_status": tenant.get("registration_status"),
            "is_active": bool(tenant.get("is_active")),
            "created_at": tenant.get("created_at").isoformat() if tenant.get("created_at") else None,
            "updated_at": tenant.get("updated_at").isoformat() if tenant.get("updated_at") else None,
        }
        if include_internal:
            result["registration_id"] = tenant.get("registration_id")
            result["metadata"] = tenant.get("metadata") or {}
        return result

    @staticmethod
    def create_pending(company_name, company_code, registration_id, metadata=None):
        now = datetime.utcnow()
        document = {
            "company_name": str(company_name).strip(),
            "company_code": normalize_company_code(company_code),
            "company_slug": slugify_company(company_name),
            "admin_user_id": None,
            "registration_id": registration_id,
            "registration_status": "pending",
            "is_active": False,
            "metadata": metadata or {},
            "created_at": now,
            "updated_at": now,
        }
        result = Tenant.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document
