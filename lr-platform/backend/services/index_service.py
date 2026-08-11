from backend.extensions import db


def _index_keys(index):
    if isinstance(index, tuple) and len(index) == 2 and isinstance(index[0], str):
        return [index]
    return index


class IndexService:
    _ensured = False

    @classmethod
    def ensure_indexes(cls):
        if cls._ensured:
            return
        try:
            for name,spec in db.servers.index_information().items():
                if spec.get("key")==[("agent_machine_id",1)]:
                    db.servers.drop_index(name)
        except:
            pass

        try:
            for name, spec in db.agent_credentials.index_information().items():
                if spec.get("key") == [
                    ("tenant_id", 1),
                    ("server_id", 1),
                    ("agent_id", 1),
                    ("server_ip", 1)
                ]:
                    db.agent_credentials.drop_index(name)
        except:
            pass
        # Drop the old global unique user indexes before creating the normal
        # lookup indexes below. Otherwise MongoDB can reject the same key
        # pattern with different uniqueness options during startup.
        try:
            for index_name, spec in db.users.index_information().items():
                keys = spec.get("key") or []
                if spec.get("unique") and keys in (
                    [("username", 1)],
                    [("email", 1)],
                ):
                    db.users.drop_index(index_name)
        except Exception:
            pass

        # Portal customization requires exactly one draft and one published
        # document per tenant. Remove a pre-release non-unique copy of the
        # same key before creating the unique index below.
        try:
            for index_name, spec in db.portal_customizations.index_information().items():
                if (
                    not spec.get("unique")
                    and (spec.get("key") or []) == [("tenant_id", 1), ("state", 1)]
                ):
                    db.portal_customizations.drop_index(index_name)
        except Exception:
            pass

        specs = {
            "tenants": [("company_code", 1), ("company_slug", 1), ("registration_status", 1), ("is_active", 1)],
            "users": [
                ("tenant_id", 1),
                ("username", 1),
                ("email", 1),
                ("role", 1),
                ("is_active", 1),
                [("is_active", 1), ("role", 1)],
                [("tenant_id", 1), ("is_active", 1), ("role", 1)],
            ],
            "rdp_sessions": [
                ("tenant_id", 1),
                ("user_id", 1),
                ("status", 1),
                ("started_at", -1),
                [("user_id", 1), ("status", 1), ("started_at", -1)],
                [("server_id", 1), ("status", 1), ("started_at", -1)],
                [("status", 1), ("last_seen_at", 1)],
                ("guac_connection_id", 1),
                [("tenant_id", 1), ("user_id", 1), ("status", 1), ("started_at", -1)],
            ],
            "activity_logs": [
                ("tenant_id", 1),
                ("user_id", 1),
                ("timestamp", -1),
                ("created_at", -1),
                [("user_id", 1), ("timestamp", -1)],
                [("tenant_id", 1), ("timestamp", -1)],
            ],
            "agents": [
                ("tenant_id", 1),
                ("username", 1),
                ("status", 1),
                ("last_seen", -1),
                [("tenant_id", 1), ("agent_id", 1)],
                [("tenant_id", 1), ("server_id", 1), ("status", 1)],
            ],
            "user_policies": [
                ("user_id", 1),
                [("tenant_id", 1), ("user_id", 1)],
            ],
            "application_assignments": [
                ("tenant_id", 1),
                ("user_id", 1),
                ("app_id", 1),
                [("user_id", 1), ("is_enabled", 1)],
                [("user_id", 1), ("is_enabled", 1), ("app_id", 1)],
                [("tenant_id", 1), ("user_id", 1), ("is_enabled", 1), ("app_id", 1)],
            ],
            "published_apps": [
                ("tenant_id", 1),
                [("server_id", 1), ("is_active", 1), ("name", 1)],
                [("is_active", 1), ("remote_app_publish_status", 1)],
                [("tenant_id", 1), ("server_id", 1), ("is_active", 1), ("name", 1)],
            ],
            "servers": [
                ("tenant_id", 1),
                [("is_active", 1), ("name", 1)],
                ("agent_id", 1),
                [("tenant_id", 1), ("is_active", 1), ("name", 1)],
            ],
            "remote_app_jobs": [
                ("tenant_id", 1),
                ("app_id", 1),
                ("server_id", 1),
                ("updated_at", 1),
                [("app_id", 1), ("action", 1)],
                [("tenant_id", 1), ("server_id", 1), ("updated_at", 1)],
            ],
            "login_links": [
                ("tenant_id", 1),
                ("user_id", 1),
                ("token", 1),
                ("created_at", -1),
                [("tenant_id", 1), ("user_id", 1), ("created_at", -1)],
            ],
            "portal_customizations": [
                ("tenant_id", 1),
                ("state", 1),
                ("updated_at", -1),
            ],
            "agent_enrollment_tokens": [[("tenant_id", 1), ("server_id", 1), ("used_at", 1)]],
            "agent_credentials": [
                [("tenant_id", 1), ("server_id", 1), ("revoked_at", 1)],
                [("agent_id", 1), ("server_ip", 1), ("revoked_at", 1)],
                ("last_used_at", -1),
            ],
            "migration_locks": [("name", 1)],
        }

        for collection_name, indexes in specs.items():
            collection = db[collection_name]
            for index in indexes:
                keys = _index_keys(index)
                try:
                    collection.create_index(keys, background=True)
                except TypeError:
                    collection.create_index(keys)

        option_indexes = (
            ("tenants", [("company_slug", 1)], {"unique": True, "name": "uq_tenants_company_slug"}),
            ("tenants", [("company_code", 1)], {
                "unique": True,
                "partialFilterExpression": {"company_code": {"$type": "string"}},
                "name": "uq_tenants_company_code",
            }),
            ("users", [("tenant_id", 1), ("username", 1)], {"unique": True, "name": "uq_users_tenant_username"}),
            ("users", [("tenant_id", 1), ("email", 1)], {
                "unique": True,
                "partialFilterExpression": {"email": {"$type": "string"}},
                "name": "uq_users_tenant_email",
            }),
            ("agent_enrollment_tokens", [("token_hash", 1)], {"unique": True, "name": "uq_agent_enrollment_token_hash"}),
            ("agent_enrollment_tokens", [("expires_at", 1)], {"expireAfterSeconds": 0, "name": "ttl_agent_enrollment"}),
            ("agent_credentials", [("tenant_id", 1), ("server_id", 1), ("agent_id", 1), ("server_ip", 1)], {
                "unique": True,
                "name": "uq_agent_credential_machine_binding",
            }),
            ("servers",
                [("agent_ip", 1)],
                    {
                        "unique": True,
                        "partialFilterExpression": {
                            "agent_ip": {"$type": "string"}
                        },
                        "name": "uq_servers_agent_ip",
                }),
            ("registration_rate_limits", [("scope_hash", 1)], {"unique": True, "name": "uq_registration_rate_scope"}),
            ("registration_rate_limits", [("expires_at", 1)], {"expireAfterSeconds": 0, "name": "ttl_registration_rate"}),
            ("portal_customizations", [("tenant_id", 1), ("state", 1)], {
                "unique": True,
                "name": "uq_portal_customization_tenant_state",
            }),
        )
        for collection_name, keys, options in option_indexes:
            try:
                db[collection_name].create_index(keys, **options)
            except TypeError:
                db[collection_name].create_index(keys)
            except Exception:
                # Legacy duplicates are reported and blocked by the explicit
                # migration preflight; they must not make an old app unbootable.
                continue
        cls._ensured = True
