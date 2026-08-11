from backend.extensions import db
from backend.tenancy.context import scoped_filter, tenant_document


class Server:

    collection = db["servers"]

    @staticmethod
    def create(data, tenant_id=None):

        server = {
            "name": data.get("name"),
            "host": data.get("host"),
            "username": data.get("username"),
            "password": data.get("password"),
            "domain": data.get("domain") or data.get("windows_domain") or data.get("hostname"),
            "port": data.get("port"),
            "agent_id": data.get("agent_id"),
            "rds_collection_name": data.get("rds_collection_name"),
            "rds_connection_broker": data.get("rds_connection_broker"),
            "is_active": data.get("is_active", True)
        }
        if tenant_id is not None:
            server = tenant_document(tenant_id, server)

        result = Server.collection.insert_one(server)
        server["_id"] = result.inserted_id
        return server

    @staticmethod
    def update(server_id, data, tenant_id=None):
        from bson import ObjectId

        data.pop("tenant_id", None)
        query = {"_id": ObjectId(server_id)}
        if tenant_id is not None:
            query = scoped_filter(tenant_id, query)
        return Server.collection.update_one(
            query,
            {"$set": data}
        )

    @staticmethod
    def delete(server_id, tenant_id=None):
        from bson import ObjectId

        query = {"_id": ObjectId(server_id)}
        if tenant_id is not None:
            query = scoped_filter(tenant_id, query)
        return Server.collection.delete_one(query)

    @staticmethod
    def get_by_id(server_id, tenant_id=None):
        from bson import ObjectId

        try:
            query = {"_id": ObjectId(server_id)}
            if tenant_id is not None:
                query = scoped_filter(tenant_id, query)
            return Server.collection.find_one(query)
        except:
            return None

    @staticmethod
    def find_all(tenant_id=None):
        return list(Server.collection.find(scoped_filter(tenant_id) if tenant_id is not None else {}))

    @staticmethod
    def find_active(tenant_id=None):
        query = {"is_active": True}
        return list(Server.collection.find(scoped_filter(tenant_id, query) if tenant_id is not None else query))

    @staticmethod
    def to_dict(server):
        return {
            "id": str(server.get("_id")),
            "tenant_id": str(server.get("tenant_id")) if server.get("tenant_id") else None,
            "name": server.get("name"),
            "host": server.get("host"),
            "username": server.get("username"),
            "domain": server.get("domain") or server.get("windows_domain") or server.get("hostname"),
            "windows_domain": server.get("domain") or server.get("windows_domain") or server.get("hostname"),
            "ip_address": server.get("host"),
            "port": server.get("port"),
            "rdp_port": server.get("port"),
            "agent_id": server.get("agent_id"),
            "agent_ip": server.get("agent_ip"),
            "agent_hostname": server.get("agent_hostname"),
            "agent_ip_addresses": server.get("agent_ip_addresses") or [],
            "agent_status": server.get("agent_status") or "offline",
            "agent_last_seen": (
                server.get("agent_last_seen").isoformat()
                if server.get("agent_last_seen")
                else None
            ),
            "rds_collection_name": server.get("rds_collection_name"),
            "rds_connection_broker": server.get("rds_connection_broker"),
            "connection_type": "rdp",
            "os_type": "Windows",
            "description": "",
            "is_active": server.get("is_active"),
            "status": "online" if server.get("is_active") else "offline",
        }
