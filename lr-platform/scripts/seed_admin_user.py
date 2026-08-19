#!/usr/bin/env python
import argparse
import os
import sys
import uuid
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core.app_factory import create_app
from backend.extensions import db
from backend.models.tenant import Tenant, normalize_company_code, slugify_company
from backend.models.user import User
from shared.security.password import hash_password


def seed_company_and_user(company_name, company_code, username, password, role="Admin"):
    app = create_app("gateway")
    with app.app_context():
        company_code = normalize_company_code(company_code or "demo")
        company_name = str(company_name or "Demo Company").strip()
        username = str(username or "admin").strip()
        password = str(password or "Password123!")

        tenant = Tenant.get_by_code(company_code)
        if not tenant:
            registration_id = uuid.uuid4().hex
            tenant = Tenant.create_pending(company_name, company_code, registration_id)
            print(f"Created pending tenant: {company_name} ({company_code})")
        else:
            print(f"Found existing tenant: {company_name} ({company_code})")

        tenant_id = tenant["_id"]
        user = User.find_by_username(username, tenant_id)
        if not user:
            user = User.create(
                username=username,
                password=hash_password(password),
                role=role,
                tenant_id=tenant_id,
                email=f"{username}@{company_code}.local",
            )
            print(f"Created user: {username} (Role: {role})")
        else:
            print(f"Found existing user: {username}")

        now = datetime.utcnow()
        Tenant.collection.update_one(
            {"_id": tenant_id},
            {"$set": {
                "admin_user_id": user.get("_id") if hasattr(user, "get") else getattr(user, "id", None),
                "registration_status": "active",
                "is_active": True,
                "updated_at": now,
            }}
        )
        print("\n==========================================")
        print("SUCCESS! Credentials ready for login:")
        print(f"Company Code: {company_code}")
        print(f"Username:     {username}")
        print(f"Password:     {password}")
        print("==========================================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed initial tenant and admin user")
    parser.add_argument("--company-name", default="Demo Company", help="Company Name")
    parser.add_argument("--company-code", default="demo", help="Company Code")
    parser.add_argument("--username", default="admin", help="Username")
    parser.add_argument("--password", default="Password123!", help="Password")
    parser.add_argument("--role", default="Admin", help="Role (Admin/User)")
    args = parser.parse_args()

    seed_company_and_user(
        args.company_name,
        args.company_code,
        args.username,
        args.password,
        args.role,
    )
