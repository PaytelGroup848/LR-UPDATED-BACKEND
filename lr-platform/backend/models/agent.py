from backend.extensions import db
from datetime import datetime


class Agent:

    collection = db["agents"]

    @staticmethod
    def create(agent_id, hostname=None, ip_address=None, username=None,
               os=None, cpu=None, ram=None, status="online"):

        agent = {
            "agent_id": agent_id,
            "hostname": hostname,
            "ip_address": ip_address,
            "username": username,
            "os": os,
            "cpu": cpu,
            "ram": ram,
            "status": status,
            "last_seen": datetime.utcnow()
        }

        existing = Agent.collection.find_one({"agent_id": agent_id})
        if existing:
            return None

        result = Agent.collection.insert_one(agent)
        agent["_id"] = result.inserted_id
        return agent

    @staticmethod
    def update_last_seen(agent_id):
        return Agent.collection.update_one(
            {"agent_id": agent_id},
            {
                "$set": {
                    "last_seen": datetime.utcnow(),
                    "status": "online"
                }
            }
        )

    @staticmethod
    def set_offline(agent_id):
        return Agent.collection.update_one(
            {"agent_id": agent_id},
            {
                "$set": {
                    "status": "offline",
                    "last_seen": datetime.utcnow()
                }
            }
        )

    @staticmethod
    def get_all():
        return list(Agent.collection.find())

    @staticmethod
    def get_by_agent_id(agent_id):
        return Agent.collection.find_one({"agent_id": agent_id})

    @staticmethod
    def delete(agent_id):
        return Agent.collection.delete_one({"agent_id": agent_id})

    # ✅ FIXED __repr__
    def __repr__(self):
        return "<Agent MongoDB Document>"