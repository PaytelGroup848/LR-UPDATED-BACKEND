import json
import secrets
from threading import Event, Lock

from backend.core.config import settings
from backend.extensions import socketio
from backend.services.agent_presence_service import AgentPresenceService


class AgentCommandService:
    RESULT_PREFIX = "lr:agent-command-result"
    _results = {}
    _events = {}
    _lock = Lock()

    @classmethod
    def call_server(
        cls,
        command,
        payload,
        *,
        tenant_id,
        server_id,
        timeout=None,
    ):
        timeout = int(timeout or settings.AGENT_COMMAND_TIMEOUT_SECONDS)
        client = AgentPresenceService.redis_client()
        presence = AgentPresenceService.get_server(tenant_id, server_id)
        target_sid = None
        if not presence:
            try:
                from backend.sockets.agent_socket import connected_agents

                target_sid = next(
                    (
                        sid
                        for sid, info in connected_agents.items()
                        if str(info.get("tenant_id")) == str(tenant_id)
                        and str(info.get("server_id")) == str(server_id)
                    ),
                    None,
                )
                if target_sid:
                    presence = dict(connected_agents[target_sid])
            except Exception:
                presence = None
        if not presence:
            return {
                "success": False,
                "message": "The Windows Agent for the selected server is offline.",
                "offline": True,
            }

        request_id = secrets.token_urlsafe(24)
        if client and target_sid is None:
            result_key = f"{cls.RESULT_PREFIX}:{request_id}"
            socketio.emit(
                "agent_command",
                {
                    "request_id": request_id,
                    "command": command,
                    "payload": payload or {},
                },
                namespace="/agent",
                to=f"server:{server_id}",
            )
            item = client.blpop(result_key, timeout=max(timeout, 1))
            if not item:
                return {
                    "success": False,
                    "message": "Windows Agent command timed out.",
                }
            try:
                return json.loads(item[1])
            finally:
                client.delete(result_key)

        # Single-worker/test fallback keeps compatibility without requiring Redis.
        try:
            if target_sid is None:
                from backend.sockets.agent_socket import connected_agents

                target_sid = next(
                    (
                        sid
                        for sid, info in connected_agents.items()
                        if str(info.get("tenant_id")) == str(tenant_id)
                        and str(info.get("server_id")) == str(server_id)
                    ),
                    None,
                )
            if target_sid:
                return socketio.call(
                    command,
                    payload or {},
                    namespace="/agent",
                    to=target_sid,
                    timeout=timeout,
                )

            # Fallback to room-level routing when direct socket targeting is unavailable.
            return socketio.call(
                command,
                payload or {},
                namespace="/agent",
                to=f"server:{server_id}",
                timeout=timeout,
            )
        except Exception as error:
            return {
                "success": False,
                "message": f"Windows Agent command failed: {error}",
            }

    @classmethod
    def publish_result(cls, request_id, result):
        request_id = str(request_id or "").strip()
        if not request_id:
            return
        client = AgentPresenceService.redis_client()
        if client:
            key = f"{cls.RESULT_PREFIX}:{request_id}"
            pipe = client.pipeline()
            pipe.rpush(key, json.dumps(result or {}, separators=(",", ":"), default=str))
            pipe.expire(key, max(int(settings.AGENT_COMMAND_TIMEOUT_SECONDS) * 2, 60))
            pipe.execute()
            return
        with cls._lock:
            cls._results[request_id] = result or {}
            event = cls._events.get(request_id)
            if event:
                event.set()
