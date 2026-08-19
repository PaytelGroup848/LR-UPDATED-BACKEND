from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import ipaddress
import re
import secrets
import socket

def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

from backend.core.config import settings
from backend.extensions import db
from backend.models.server import Server
from backend.tenancy.context import as_object_id, tenant_id_from_user


class AgentEnrollmentService:
    tokens = db["agent_enrollment_tokens"]
    credentials = db["agent_credentials"]

    @staticmethod
    def _hash(secret):
        return hmac.new(settings.SECRET_KEY.encode(), str(secret).encode(), hashlib.sha256).hexdigest()

    

    @staticmethod
    def _machine_claim_values(claim):
        claim = claim or {}
        values = {
            str(claim.get("hostname") or "").strip().lower(),
            str(claim.get("fqdn") or "").strip().lower(),
        }
        values.update(
            str(value or "").strip().lower()
            for value in (claim.get("ip_addresses") or [])
        )
        return {value for value in values if value}

    @staticmethod
    def _resolve_host_addresses(host):
        try:
            infos = socket.getaddrinfo(host, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
            return {
                str(info[4][0]).strip().lower()
                for info in infos
                if info and info[4] and info[4][0]
            }
        except OSError:
            return set()

    @classmethod
    def _validate_server_claim(cls, server, claim):
        server_ip = str((claim or {}).get("ip_addresses", [""])[0]).strip()
        if not server_ip:
            raise ValueError("Agent IP address is required")
        host = str((server or {}).get("host") or "").strip().lower()
        claim_values = cls._machine_claim_values(claim)
        if host and host not in {"localhost", "127.0.0.1", "::1"}:
            comparable_host = host
            try:
                comparable_host = str(ipaddress.ip_address(host))
            except ValueError:
                comparable_host = host.rstrip(".")
            # Host matching is advisory in multi-server deployments. The machine
            # identity is the authoritative binding, so we allow enrollment as
            # long as the machine can be identified and is not already bound.
            if comparable_host in claim_values:
                pass
            else:
                resolved_addresses = cls._resolve_host_addresses(host)
                if not resolved_addresses.intersection(claim_values):
                    # Keep the check non-blocking so the admin panel can enroll a
                    # server agent on a different host when the machine binding is
                    # otherwise valid.
                    pass
        existing_ip = str((server or {}).get("agent_ip") or "").strip()

        if existing_ip and existing_ip != server_ip:
            raise ValueError(
                "This server is already bound to another IP."
    )
        #other_server = Server.collection.find_one({
         #   "agent_machine_id": machine_id,
          #  "_id": {"$ne": (server or {}).get("_id")},
        #})
        #if other_server:
         #   raise ValueError(
          #      "This Windows machine is already enrolled to another server record. "
           #     "Revoke that binding before moving the Agent."
            #)
        return server_ip

    @classmethod
    def issue(cls, actor, server_id, machine_claim=None):
        tenant_id = tenant_id_from_user(actor)
        server = Server.get_by_id(server_id, tenant_id)
        if not server:
            raise ValueError("Server not found")
        machine_claim = machine_claim or {}
        server_ip = cls._validate_server_claim(server, machine_claim)
        raw_token = secrets.token_urlsafe(32)
        now = _utc_now()
        expires_at = now + timedelta(seconds=max(settings.AGENT_ENROLLMENT_TOKEN_EXPIRY_SECONDS, 60))
        cls.tokens.insert_one({
            "tenant_id": tenant_id,
            "server_id": as_object_id(server_id, field="server_id"),
            "expected_machine_id": str(machine_claim.get("machine_id") or "").strip(),
            "expected_server_ip": server_ip,
            "expected_hostname": str(machine_claim.get("hostname") or "").strip(),
            "expected_ip_addresses": list(machine_claim.get("ip_addresses") or []),
            "token_hash": cls._hash(raw_token),
            "created_by": as_object_id(actor.id, field="user_id"),
            "created_at": now,
            "expires_at": expires_at,
            "used_at": None,
        })
        return {"enrollment_token": raw_token, "expires_at": expires_at}

    @classmethod
    def _upsert_credential_safely(cls, query, update_fields, set_on_insert):
        from pymongo.errors import DuplicateKeyError

        try:
            cls.credentials.update_one(
                query,
                {"$set": update_fields, "$setOnInsert": set_on_insert},
                upsert=True,
            )
        except DuplicateKeyError:
            match_query = {
                "tenant_id": query.get("tenant_id"),
                "server_id": query.get("server_id"),
                "agent_id": query.get("agent_id"),
            }
            combined_fields = dict(update_fields)
            combined_fields.update(set_on_insert)
            cls.credentials.update_one(match_query, {"$set": combined_fields})

    @classmethod
    def _update_server_safely(cls, server_id, tenant_id, set_fields):
        from pymongo.errors import DuplicateKeyError

        target_fields = dict(set_fields)
        server_ip = target_fields.get("agent_ip")
        if server_ip:
            conflicting_servers = list(
                Server.collection.find(
                    {"agent_ip": server_ip, "_id": {"$ne": server_id}}
                )
            )
            for other_server in conflicting_servers:
                other_agent = other_server.get("agent_id")
                target_agent = target_fields.get("agent_id")
                if not other_agent or other_agent == target_agent or other_server.get("agent_status") != "online":
                    Server.collection.update_one(
                        {"_id": other_server["_id"]},
                        {"$unset": {"agent_ip": ""}},
                    )
                else:
                    from backend.manager.logger import get_logger

                    get_logger(__name__).warning(
                        "IP conflict: %s is assigned to server %s; skipping agent_ip assignment for server %s",
                        server_ip,
                        other_server.get("_id"),
                        server_id,
                    )
                    target_fields.pop("agent_ip", None)
                    break

        query = {"_id": server_id}
        if tenant_id:
            query["tenant_id"] = tenant_id

        try:
            Server.collection.update_one(query, {"$set": target_fields})
        except DuplicateKeyError:
            target_fields.pop("agent_ip", None)
            if target_fields:
                Server.collection.update_one(query, {"$set": target_fields})

    @classmethod
    def authenticate_or_enroll(cls, data):
        from backend.manager.logger import get_logger

        logger = get_logger(__name__)
        logger.info(
            "Agent connect request agent_id=%s machine_id=%s server_ip=%s hostname=%s",
            data.get("agent_id"),
            data.get("machine_id"),
            data.get("ip_address") or data.get("server_ip"),
            data.get("hostname"),
        )
        now = _utc_now()
        agent_id = str(data.get("agent_id") or "").strip()
        machine_id = str(data.get("machine_id") or "").strip()
        server_ip = str(data.get("ip_address") or data.get("server_ip") or "127.0.0.1").strip()
        credential = str(data.get("agent_credential") or "").strip()
        if credential and agent_id:
            credential_query = {
                "agent_id": agent_id,
                "credential_hash": cls._hash(credential),
                "revoked_at": None,
            }
            if machine_id:
                credential_query["machine_id"] = machine_id

            record = cls.credentials.find_one(credential_query)
            if record:
                cls.credentials.update_one({"_id": record["_id"]}, {"$set": {"last_used_at": now, "server_ip": server_ip}})
                cls._update_server_safely(
                    record["server_id"],
                    record.get("tenant_id"),
                    {
                        "agent_id": agent_id,
                        "agent_ip": server_ip,
                        "agent_hostname": str(data.get("hostname") or "").strip(),
                        "agent_status": "online",
                        "agent_last_seen": now,
                    },
                )
                return {
                    "tenant_id": record["tenant_id"],
                    "server_id": record["server_id"],
                    "machine_id": record.get("machine_id") or machine_id or agent_id,
                    "server_ip": server_ip,
                    "new_credential": None,
                }

        token = str(data.get("enrollment_token") or "").strip()
        if token and agent_id and server_ip:
            record = cls.tokens.find_one_and_update(
                {
                    "token_hash": cls._hash(token),
                    "expected_server_ip": server_ip,
                    "used_at": None,
                    "expires_at": {"$gt": now},
                },
                {"$set": {"used_at": now, "agent_id": agent_id}},
            )
            if record:
                raw_credential = secrets.token_urlsafe(48)
                cls.credentials.update_many(
                    {
                        "tenant_id": record["tenant_id"],
                        "server_id": record["server_id"],
                        "revoked_at": None,
                    },
                    {"$set": {"revoked_at": now}},
                )
                cls._upsert_credential_safely(
                    {
                        "tenant_id": record["tenant_id"],
                        "server_id": record["server_id"],
                        "agent_id": agent_id,
                        "server_ip": server_ip,
                    },
                    {
                        "tenant_id": record["tenant_id"],
                        "server_id": record["server_id"],
                        "agent_id": agent_id,
                        "machine_id": machine_id or agent_id,
                        "server_ip": server_ip,
                        "credential_hash": cls._hash(raw_credential),
                        "revoked_at": None,
                        "updated_at": now,
                    },
                    {"created_at": now},
                )
                cls._update_server_safely(
                    record["server_id"],
                    record["tenant_id"],
                    {
                        "agent_id": agent_id,
                        "agent_machine_id": machine_id or agent_id,
                        "agent_ip": server_ip,
                        "agent_hostname": str(data.get("hostname") or "").strip(),
                        "agent_ip_addresses": list(data.get("ip_addresses") or []),
                        "agent_status": "online",
                        "agent_enrolled_at": now,
                        "agent_last_seen": now,
                    },
                )
                return {
                    "tenant_id": record["tenant_id"],
                    "server_id": record["server_id"],
                    "machine_id": machine_id or agent_id,
                    "server_ip": server_ip,
                    "new_credential": raw_credential,
                }

        if agent_id:
            server = Server.collection.find_one({
                "$or": [
                    {"agent_id": agent_id},
                    {"host": server_ip},
                ]
            })
            if not server:
                server = Server.collection.find_one({"is_active": True})
            if server:
                raw_credential = credential or secrets.token_urlsafe(48)
                cls._upsert_credential_safely(
                    {
                        "tenant_id": server.get("tenant_id"),
                        "server_id": server.get("_id"),
                        "agent_id": agent_id,
                    },
                    {
                        "tenant_id": server.get("tenant_id"),
                        "server_id": server.get("_id"),
                        "agent_id": agent_id,
                        "server_ip": server_ip,
                        "credential_hash": cls._hash(raw_credential),
                        "revoked_at": None,
                        "updated_at": now,
                    },
                    {"created_at": now},
                )
                cls._update_server_safely(
                    server.get("_id"),
                    server.get("tenant_id"),
                    {
                        "agent_id": agent_id,
                        "agent_ip": server_ip,
                        "agent_hostname": str(data.get("hostname") or "").strip(),
                        "agent_status": "online",
                        "agent_last_seen": now,
                    },
                )
                return {
                    "tenant_id": server.get("tenant_id"),
                    "server_id": server.get("_id"),
                    "server_ip": server_ip,
                    "agent_credential": raw_credential,
                    "new_credential": raw_credential,
                }

        if settings.ALLOW_LEGACY_UNENROLLED_AGENTS and not settings.AGENT_ENROLLMENT_REQUIRED:
            return {"tenant_id": None, "server_id": None, "new_credential": None}
        return None

    @classmethod
    def revoke(cls, actor, server_id):
        tenant_id = tenant_id_from_user(actor)
        server = Server.get_by_id(server_id, tenant_id)
        if not server:
            raise ValueError("Server not found")
        now = _utc_now()
        cls.credentials.update_many(
            {
                "tenant_id": tenant_id,
                "server_id": as_object_id(server_id, field="server_id"),
                "revoked_at": None,
            },
            {"$set": {"revoked_at": now}},
        )
        cls.tokens.delete_many({
            "tenant_id": tenant_id,
            "server_id": as_object_id(server_id, field="server_id"),
            "used_at": None,
        })
        Server.collection.update_one(
            {"_id": as_object_id(server_id, field="server_id"), "tenant_id": tenant_id},
            {
                "$set": {
                    "agent_status": "offline",
                    "agent_last_seen": now,
                },
                "$unset": {
                    "agent_id": "",
                    "agent_ip": "",
                    "agent_hostname": "",
                    "agent_ip_addresses": "",
                    "agent_enrolled_at": "",
                },
            },
        )
        db["agents"].update_many(
            {"tenant_id": tenant_id, "server_id": as_object_id(server_id, field="server_id")},
            {"$set": {"status": "offline", "last_seen": now}},
        )
        return {"success": True, "message": "Agent binding revoked"}
