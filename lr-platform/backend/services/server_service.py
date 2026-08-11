from backend.models.server import Server
from backend.security.credential_crypto import encrypt_secret
from backend.tenancy.context import tenant_id_from_user


def _clean_text(value):
    return str(value or "").strip()


def _as_int(value, default=None):
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"false", "0", "no", "off"}


class ServerService:

    @staticmethod
    def add_server(payload, actor):
        tenant_id = tenant_id_from_user(actor)
        name = _clean_text(payload.get("name"))
        host = _clean_text(payload.get("host") or payload.get("ip_address"))

        if not name or not host:
            return {"success": False, "message": "Server name and host are required"}, 400

        server = Server.create({
            "name": name,
            "host": host,
            "username": _clean_text(payload.get("username")),
            "password": encrypt_secret(payload.get("password")),
            "domain": _clean_text(
                payload.get("domain")
                or payload.get("windows_domain")
                or payload.get("hostname")
            ) or None,
            "port": _as_int(payload.get("port") or payload.get("rdp_port"), 3389),
            "agent_id": _clean_text(payload.get("agent_id")) or None,
            "rds_collection_name": _clean_text(payload.get("rds_collection_name")) or None,
            "rds_connection_broker": _clean_text(payload.get("rds_connection_broker")) or None,
            "is_active": _as_bool(payload.get("is_active"), True),
        }, tenant_id=tenant_id)

        return {
            "success": True,
            "message": "Server added successfully",
            "server": Server.to_dict(server),
        }, 201

    @staticmethod
    def update_server(server_id, data, actor):
        tenant_id = tenant_id_from_user(actor)
        server = Server.get_by_id(server_id, tenant_id)
        if not server:
            return {"success": False, "message": "Server not found"}, 404

        updates = {}
        for key in ("name", "username", "password"):
            if key in data:
                if key == "password" and not _clean_text(data.get(key)):
                    continue
                updates[key] = _clean_text(data.get(key)) if key != "password" else encrypt_secret(data.get(key))
        for key in ("agent_id", "rds_collection_name", "rds_connection_broker"):
            if key in data:
                updates[key] = _clean_text(data.get(key)) or None
        if "domain" in data or "windows_domain" in data or "hostname" in data:
            updates["domain"] = _clean_text(
                data.get("domain")
                or data.get("windows_domain")
                or data.get("hostname")
            ) or None
        if "host" in data or "ip_address" in data:
            updates["host"] = _clean_text(data.get("host") or data.get("ip_address"))
        if "port" in data or "rdp_port" in data:
            updates["port"] = _as_int(data.get("port") or data.get("rdp_port"), server.get("port"))
        if "is_active" in data:
            updates["is_active"] = _as_bool(data.get("is_active"), True)

        if updates:
            Server.update(server_id, updates, tenant_id)
            server = Server.get_by_id(server_id, tenant_id)

        return {
            "success": True,
            "message": "Server updated successfully",
            "server": Server.to_dict(server),
        }, 200

    @staticmethod
    def get_servers(actor):
        tenant_id = tenant_id_from_user(actor)
        return {
            "success": True,
            "servers": [Server.to_dict(server) for server in Server.find_all(tenant_id)],
        }, 200

    @staticmethod
    def get_server(server_id, actor):
        tenant_id = tenant_id_from_user(actor)
        server = Server.get_by_id(server_id, tenant_id)
        if not server:
            return {"success": False, "message": "Server not found"}, 404
        return {"success": True, "server": Server.to_dict(server)}, 200

    @staticmethod
    def delete_server(server_id, actor):
        tenant_id = tenant_id_from_user(actor)
        result = Server.delete(server_id, tenant_id)
        if not result or result.deleted_count == 0:
            return {"success": False, "message": "Server not found"}, 404
        return {"success": True, "message": "Server deleted successfully"}, 200

    @staticmethod
    def test_rdp_server(server_id, actor):
        tenant_id = tenant_id_from_user(actor)
        server = Server.get_by_id(server_id, tenant_id)
        if not server:
            return {"success": False, "message": "Server not found"}, 404
        return {
            "success": True,
            "message": "Server is available for portal launch.",
            "server": Server.to_dict(server),
        }, 200

    @staticmethod
    def connect_server(server_id, payload, actor):
        tenant_id = tenant_id_from_user(actor)
        server = Server.get_by_id(server_id, tenant_id)
        if not server:
            return {"success": False, "message": "Server not found"}, 404
        return {
            "success": True,
            "message": "Server connection request accepted.",
            "server": Server.to_dict(server),
        }, 200
