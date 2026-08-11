"""Explicit, idempotent migration from the legacy shared dataset to one tenant.

Dry-run is the default. Applying requires an explicit company name and the
username of the legacy administrator who will own the tenant.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import sys
import uuid

from pymongo.errors import DuplicateKeyError

from backend.extensions import db
from backend.models.tenant import normalize_company_code, slugify_company


DIRECT_COLLECTIONS = (
    "users", "servers", "published_apps", "application_assignments",
    "sessions", "rdp_sessions", "login_links", "agents", "activity_logs",
    "logs", "user_policies", "remote_app_jobs", "desktop_shortcut_jobs",
    "tickets", "clipboard_entries", "license_activations", "trial_sessions",
)


def _missing_filter():
    return {"$or": [{"tenant_id": {"$exists": False}}, {"tenant_id": None}]}


def _duplicate_values(collection_name, field):
    pipeline = [
        {"$match": {field: {"$nin": [None, ""]}}},
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}},
        {"$limit": 25},
    ]
    return list(db[collection_name].aggregate(pipeline))


def build_report(company_name=None, admin_username=None, company_code=None):
    resolved_company_code = normalize_company_code(company_code) or (
        slugify_company(company_name) if company_name else None
    )
    report = {
        "mode": "dry-run",
        "company_name": company_name,
        "company_slug": slugify_company(company_name) if company_name else None,
        "company_code": resolved_company_code,
        "admin_username": admin_username,
        "collections": {},
        "duplicates": {
            "usernames": _duplicate_values("users", "username"),
            "emails": _duplicate_values("users", "email"),
        },
        "unresolved": [],
    }
    for name in DIRECT_COLLECTIONS:
        report["collections"][name] = db[name].count_documents(_missing_filter())

    if admin_username:
        admins = list(db.users.find({"username": admin_username}, {"_id": 1, "role": 1}))
        if len(admins) != 1:
            report["unresolved"].append({
                "type": "admin_username",
                "value": admin_username,
                "matches": len(admins),
            })
    return report


def _acquire_lock(run_id):
    now = datetime.utcnow()
    try:
        db.migration_locks.insert_one({
            "_id": "multi_tenancy_v1",
            "name": "multi_tenancy_v1",
            "run_id": run_id,
            "status": "running",
            "started_at": now,
        })
    except DuplicateKeyError as exc:
        existing = db.migration_locks.find_one({"_id": "multi_tenancy_v1"}) or {}
        if existing.get("status") == "complete":
            return False
        if existing.get("status") == "failed":
            result = db.migration_locks.update_one(
                {"_id": "multi_tenancy_v1", "status": "failed"},
                {
                    "$set": {
                        "run_id": run_id,
                        "status": "running",
                        "started_at": now,
                    },
                    "$unset": {
                        "failed_at": "",
                        "error": "",
                    },
                },
            )
            if result.modified_count == 1:
                return True
        raise RuntimeError("Another multi-tenancy migration is running") from exc
    return True


def _ensure_tenant(company_name, company_code, admin_username, run_id):
    slug = slugify_company(company_name)
    tenant = db.tenants.find_one({"company_slug": slug})
    if tenant:
        return tenant
    now = datetime.utcnow()
    document = {
        "company_name": company_name.strip(),
        "company_code": normalize_company_code(company_code) or slug,
        "company_slug": slug,
        "admin_user_id": None,
        "registration_id": f"migration:{run_id}",
        "registration_status": "migrating",
        "is_active": False,
        "metadata": {"source": "legacy_migration", "admin_username": admin_username},
        "created_at": now,
        "updated_at": now,
    }
    result = db.tenants.insert_one(document)
    document["_id"] = result.inserted_id
    return document


def _create_indexes():
    db.tenants.create_index([("company_slug", 1)], unique=True, name="uq_tenants_company_slug")
    db.tenants.create_index(
        [("company_code", 1)],
        unique=True,
        partialFilterExpression={"company_code": {"$type": "string"}},
        name="uq_tenants_company_code",
    )
    for index_name, spec in db.users.index_information().items():
        if spec.get("unique") and (spec.get("key") or []) in (
            [("username", 1)],
            [("email", 1)],
        ):
            db.users.drop_index(index_name)
    db.users.create_index(
        [("tenant_id", 1), ("username", 1)],
        unique=True,
        name="uq_users_tenant_username",
    )
    db.users.create_index(
        [("tenant_id", 1), ("email", 1)],
        unique=True,
        partialFilterExpression={"email": {"$type": "string"}},
        name="uq_users_tenant_email",
    )
    for name in DIRECT_COLLECTIONS:
        # Reuse an existing equivalent index regardless of its generated name.
        db[name].create_index([("tenant_id", 1)])
    db.agent_enrollment_tokens.create_index(
        [("token_hash", 1)],
        unique=True,
        name="uq_agent_enrollment_token_hash",
    )
    _ensure_ttl_index(
        db.agent_enrollment_tokens,
        [("expires_at", 1)],
        "ttl_agent_enrollment",
    )
    db.registration_rate_limits.create_index(
        [("scope_hash", 1)],
        unique=True,
        name="uq_registration_rate_scope",
    )
    _ensure_ttl_index(
        db.registration_rate_limits,
        [("expires_at", 1)],
        "ttl_registration_rate",
    )


def _ensure_ttl_index(collection, keys, name):
    expected_keys = list(keys)
    conflicts = []
    for index_name, spec in collection.index_information().items():
        if spec.get("key") != expected_keys:
            continue
        if spec.get("expireAfterSeconds") == 0:
            return index_name
        conflicts.append(index_name)

    for index_name in conflicts:
        collection.drop_index(index_name)
    return collection.create_index(keys, expireAfterSeconds=0, name=name)


def apply(company_name, admin_username, company_code=None):
    if not company_name or not slugify_company(company_name):
        raise ValueError("--company-name is required with --apply")
    if not admin_username:
        raise ValueError("--admin-username is required with --apply")

    resolved_company_code = normalize_company_code(company_code) or slugify_company(company_name)
    report = build_report(company_name, admin_username, resolved_company_code)
    if report["duplicates"]["usernames"] or report["duplicates"]["emails"] or report["unresolved"]:
        raise RuntimeError("Preflight failed; resolve duplicate/unresolved records shown by --dry-run")

    run_id = uuid.uuid4().hex
    if not _acquire_lock(run_id):
        report["mode"] = "apply"
        report["already_complete"] = True
        return report

    tenant = _ensure_tenant(company_name, resolved_company_code, admin_username, run_id)
    tenant_id = tenant["_id"]
    try:
        updated = {}
        for name in DIRECT_COLLECTIONS:
            result = db[name].update_many(_missing_filter(), {"$set": {"tenant_id": tenant_id}})
            updated[name] = result.modified_count

        admin = db.users.find_one({"tenant_id": tenant_id, "username": admin_username})
        if not admin:
            raise RuntimeError("Selected legacy administrator was not found after assignment")
        now = datetime.utcnow()
        db.tenants.update_one(
            {"_id": tenant_id},
            {"$set": {
                "admin_user_id": admin["_id"],
                "registration_status": "active",
                "is_active": True,
                "updated_at": now,
            }},
        )
        _create_indexes()
        db.migration_locks.update_one(
            {"_id": "multi_tenancy_v1", "run_id": run_id},
            {"$set": {"status": "complete", "tenant_id": tenant_id, "completed_at": now, "updated": updated}},
        )
        report.update({"mode": "apply", "tenant_id": str(tenant_id), "updated": updated})
        return report
    except Exception as exc:
        db.migration_locks.update_one(
            {"_id": "multi_tenancy_v1", "run_id": run_id},
            {"$set": {"status": "failed", "failed_at": datetime.utcnow(), "error": str(exc)[:1000]}},
        )
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Migrate LR Platform data to tenant ownership")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Inspect only (default)")
    mode.add_argument("--apply", action="store_true", help="Apply the migration")
    parser.add_argument("--company-name")
    parser.add_argument("--company-code")
    parser.add_argument("--admin-username")
    args = parser.parse_args(argv)
    try:
        result = (
            apply(args.company_name, args.admin_username, args.company_code)
            if args.apply
            else build_report(args.company_name, args.admin_username, args.company_code)
        )
        print(json.dumps(result, default=str, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
