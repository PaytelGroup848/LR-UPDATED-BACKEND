from datetime import datetime

from backend.models.tenant import Tenant, normalize_company_code, slugify_company
from backend.tenancy.context import as_object_id


class TenantRepository:
    def __init__(self, database):
        self.collection = database["tenants"]

    def get_by_id(self, tenant_id):
        return self.collection.find_one({"_id": as_object_id(tenant_id)})

    def get_by_slug(self, slug):
        return self.collection.find_one({"company_slug": slugify_company(slug)})

    def get_by_code(self, company_code):
        code = normalize_company_code(company_code)
        tenant = self.collection.find_one({"company_code": code}) if code else None
        if tenant:
            return tenant
        return self.collection.find_one({
            "company_code": {"$in": [None, ""]},
            "company_slug": slugify_company(code),
        }) if code else None

    def create_pending(self, company_name, company_code, registration_id, metadata=None):
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
        result = self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    def finalize(self, tenant_id, admin_user_id):
        self.collection.update_one(
            {"_id": as_object_id(tenant_id), "registration_status": "pending"},
            {"$set": {
                "admin_user_id": as_object_id(admin_user_id, field="admin_user_id"),
                "registration_status": "active",
                "is_active": True,
                "updated_at": datetime.utcnow(),
            }},
        )
        return self.get_by_id(tenant_id)

    def delete_pending(self, tenant_id, registration_id):
        return self.collection.delete_one({
            "_id": as_object_id(tenant_id),
            "registration_id": registration_id,
            "registration_status": "pending",
        })

    @staticmethod
    def serialize(document):
        return Tenant.to_dict(document)
