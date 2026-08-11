from datetime import datetime, timedelta

from backend.models.agent import Agent
from backend.tenancy.context import scoped_filter, tenant_id_from_user


def _serialize(agent):
    if not agent:
        return None

    last_seen = agent.get("last_seen")
    status = agent.get("status") or "offline"
    if last_seen and datetime.utcnow() - last_seen > timedelta(seconds=45):
        status = "offline"

    return {
        "id": str(agent.get("_id")) if agent.get("_id") else None,
        "agent_id": agent.get("agent_id"),
        "hostname": agent.get("hostname"),
        "ip_address": agent.get("ip_address"),
        "username": agent.get("username"),
        "os": agent.get("os"),
        "cpu": agent.get("cpu"),
        "ram": agent.get("ram"),
        "status": status,
        "last_seen": last_seen.isoformat() if last_seen else None,
        "recording": bool(agent.get("recording")),
    }


class AgentService:

    @staticmethod
    def get_agents(actor, username=None):
        tenant_id = tenant_id_from_user(actor)
        query = {}
        if username:
            query["username"] = str(username)
        query = scoped_filter(tenant_id, query)
        return {
            "success": True,
            "agents": [_serialize(agent) for agent in Agent.collection.find(query).sort("last_seen", -1).limit(500)],
        }

    @staticmethod
    def get_agent(agent_id, actor):
        tenant_id = tenant_id_from_user(actor)
        agent = Agent.collection.find_one(scoped_filter(tenant_id, {"agent_id": agent_id}))
        if not agent:
            return {
                "success": False,
                "error": "Agent not found"
            }
        return {
            "success": True,
            "agent": _serialize(agent),
        }
