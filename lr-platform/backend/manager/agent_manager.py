from backend.models.agent import Agent
from backend.models.server import Server
from backend.extensions import db
from backend.manager.logger import get_logger
from datetime import datetime

logger = get_logger(__name__)


def register_agent(agent_id, hostname, ip_address, username, os, cpu, ram, tenant_id=None, server_id=None):
    try:
        query = {"agent_id": agent_id}
        if tenant_id is not None:
            query["tenant_id"] = tenant_id
        agent = Agent.collection.find_one(query)
        if agent:
            Agent.collection.update_one(
                query,
                {
                    "$set": {
                        "hostname": hostname,
                        "ip_address": ip_address,
                        "username": username,
                        "os": os,
                        "cpu": cpu,
                        "ram": ram,
                        "status": "online",
                        "last_seen": datetime.utcnow()
                        ,"tenant_id": tenant_id
                        ,"server_id": server_id
                    }
                }
            )
        else:
            created = Agent.create(
            agent_id=agent_id,
            hostname=hostname,
            ip_address=ip_address,
            username=username,
            os=os,
            cpu=cpu,
            ram=ram,
            status="online"
            )
            if created and tenant_id is not None:
                Agent.collection.update_one(
                    {"_id": created["_id"]},
                    {"$set": {"tenant_id": tenant_id, "server_id": server_id}},
                )
        if tenant_id is not None and server_id is not None:
            Server.collection.update_one(
                {"_id": server_id, "tenant_id": tenant_id},
                {"$set": {
                    "agent_id": agent_id,
                    "agent_hostname": hostname,
                    "agent_status": "online",
                    "agent_last_seen": datetime.utcnow(),
                }},
            )
    except Exception as error:
        logger.warning("Agent registration update skipped due to database error: %s", error)


def update_heartbeat(agent_id, tenant_id=None):
    try:
        query = {"agent_id": agent_id}
        if tenant_id is not None:
            query["tenant_id"] = tenant_id
        agent = Agent.collection.find_one(query)
        if agent:
            Agent.collection.update_one(
                query,
                {
                    "$set": {
                        "status": "online",
                        "last_seen": datetime.utcnow()
                    }
                }
            )
            if agent.get("server_id") is not None and tenant_id is not None:
                Server.collection.update_one(
                    {"_id": agent.get("server_id"), "tenant_id": tenant_id},
                    {"$set": {
                        "agent_status": "online",
                        "agent_last_seen": datetime.utcnow(),
                    }},
                )
    except Exception as error:
        logger.warning("Agent heartbeat update skipped due to database error: %s", error)


def set_offline(agent_id, tenant_id=None):
    try:
        query = {"agent_id": agent_id}
        if tenant_id is not None:
            query["tenant_id"] = tenant_id
        agent = Agent.collection.find_one(query)
        if agent:
            Agent.collection.update_one(
                query,
                {
                    "$set": {
                        "status": "offline",
                        "last_seen": datetime.utcnow()
                    }
                }
            )
            if agent.get("server_id") is not None and tenant_id is not None:
                Server.collection.update_one(
                    {
                        "_id": agent.get("server_id"),
                        "tenant_id": tenant_id,
                        "agent_id": agent_id,
                    },
                    {"$set": {
                        "agent_status": "offline",
                        "agent_last_seen": datetime.utcnow(),
                    }},
                )
    except Exception as error:
        logger.warning("Agent offline update skipped due to database error: %s", error)
