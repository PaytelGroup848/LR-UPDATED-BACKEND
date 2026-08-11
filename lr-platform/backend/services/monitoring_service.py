import os
import time
from datetime import datetime

import psutil
from flask import current_app

from backend.extensions import db
from backend.manager.stream_manager import stream_manager
from backend.models.agent import Agent
from backend.models.rdp_session import RdpSession


_MONITORING_CACHE = {}


def _iso(value):
    return value.isoformat() if value else None


class MonitoringService:
    @staticmethod
    def get_health(tenant_id=None):
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(os.getcwd())
        network = psutil.net_io_counters()
        tenant_query = {"tenant_id": tenant_id} if tenant_id is not None else {}
        active_sessions = RdpSession.collection.count_documents({**tenant_query, "status": "active"})
        total_agents = Agent.collection.count_documents(tenant_query)
        online_agents = Agent.collection.count_documents({**tenant_query, "status": "online"})
        return {
            "status": "healthy",
            "checked_at": datetime.utcnow().isoformat(),
            "process": {
                "pid": os.getpid(),
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_percent": memory.percent,
                "disk_percent": disk.percent,
                "network_sent_mb": round(network.bytes_sent / 1024 / 1024, 1),
                "network_recv_mb": round(network.bytes_recv / 1024 / 1024, 1),
            },
            "sessions": {
                "active": active_sessions,
                "total": RdpSession.collection.count_documents(tenant_query),
            },
            "agents": {
                "online": online_agents,
                "total": total_agents,
            },
        }

    @staticmethod
    def get_service_status():
        services = {
            "backend": {"status": "ok", "message": "API responding"},
            "database": {"status": "unknown", "message": "Not checked"},
            "guacamole": {"status": "unknown", "message": "Not checked"},
            "api": {"status": "ok", "message": "Routes loaded"},
            "license": {"status": "unknown", "message": "Not checked"},
        }

        try:
            db.command("ping")
            services["database"] = {"status": "ok", "message": "MongoDB ping OK"}
        except Exception as error:
            services["database"] = {"status": "error", "message": str(error)}

        try:
            required = ("GUACAMOLE_URL", "GUACAMOLE_USER", "GUACAMOLE_PASSWORD")
            missing = [key for key in required if not current_app.config.get(key)]
            if missing:
                services["guacamole"] = {
                    "status": "warning",
                    "message": f"Missing config: {', '.join(missing)}",
                }
            else:
                services["guacamole"] = {"status": "ok", "message": "Configured"}
        except RuntimeError:
            services["guacamole"] = {"status": "warning", "message": "No app context"}

        try:
            db["product_keys"].estimated_document_count()
            services["license"] = {"status": "ok", "message": "License storage OK"}
        except Exception as error:
            services["license"] = {"status": "error", "message": str(error)}

        return services

    @staticmethod
    def get_agents_summary(tenant_id=None):
        agents = []
        query = {"tenant_id": tenant_id} if tenant_id is not None else {}
        for agent in Agent.collection.find(query).sort("last_seen", -1):
            agents.append({
                "agent_id": agent.get("agent_id"),
                "hostname": agent.get("hostname"),
                "status": agent.get("status"),
                "last_seen": _iso(agent.get("last_seen")),
            })
        return {
            "items": agents,
            "total": len(agents),
            "online": sum(1 for agent in agents if agent.get("status") == "online"),
        }

    @staticmethod
    def get_streams(agent_id=None, tenant_id=None):
        streams = stream_manager.status()
        if tenant_id is not None:
            tenant_agents = {
                item.get("agent_id")
                for item in Agent.collection.find({"tenant_id": tenant_id}, {"agent_id": 1})
            }
            streams = [item for item in streams if item.get("agent_id") in tenant_agents]
        if agent_id:
            streams = [item for item in streams if item.get("agent_id") == agent_id]
        return {
            "items": streams,
            "total": len(streams),
        }

    @staticmethod
    def get_monitoring(tenant_id=None):
        now = time.monotonic()
        cache_key = str(tenant_id or "")
        cached = _MONITORING_CACHE.get(cache_key)
        if cached and cached["expires_at"] > now:
            return cached["data"]

        data = {
            "success": True,
            "health": MonitoringService.get_health(tenant_id),
            "agents": MonitoringService.get_agents_summary(tenant_id),
            "streams": MonitoringService.get_streams(tenant_id=tenant_id),
            "services": MonitoringService.get_service_status(),
        }
        _MONITORING_CACHE[cache_key] = {"expires_at": now + 3, "data": data}
        return data

    @staticmethod
    def get_monitoring_uncached(tenant_id=None):
        return {
            "success": True,
            "health": MonitoringService.get_health(tenant_id),
            "agents": MonitoringService.get_agents_summary(tenant_id),
            "streams": MonitoringService.get_streams(tenant_id=tenant_id),
            "services": MonitoringService.get_service_status(),
        }
