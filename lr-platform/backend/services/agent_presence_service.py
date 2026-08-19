import json
from threading import Lock
from time import monotonic

from backend.core.config import settings


class AgentPresenceService:
    PREFIX = "lr:agent-presence"
    _memory = {}
    _lock = Lock()
    _redis = None
    _redis_checked = False
    _redis_retry_at = 0.0

    @classmethod
    def _ttl(cls):
        return max(settings.AGENT_PRESENCE_TTL_SECONDS, 30)

    @classmethod
    def _redis_url(cls):
        return (
            (settings.AGENT_PRESENCE_REDIS_URL or "").strip()
            or (settings.SOCKETIO_MESSAGE_QUEUE or "").strip()
        )

    @classmethod
    def redis_client(cls):
        now = monotonic()
        if cls._redis is not None:
            return cls._redis
        if cls._redis_checked and now < cls._redis_retry_at:
            return None
        cls._redis_checked = True
        url = cls._redis_url()
        if not url.startswith(("redis://", "rediss://")):
            return None
        try:
            import redis

            client = redis.Redis.from_url(url, decode_responses=True)
            client.ping()
            cls._redis = client
        except Exception:
            cls._redis = None
            cls._redis_retry_at = now + 5.0
        return cls._redis

    @classmethod
    def _server_key(cls, tenant_id, server_id):
        return f"{cls.PREFIX}:server:{tenant_id}:{server_id}"

    @classmethod
    def _agent_key(cls, tenant_id, agent_id):
        return f"{cls.PREFIX}:agent:{tenant_id}:{agent_id}"

    @classmethod
    def register(cls, info):
        source = dict(info or {})
        payload = {}
        for key, value in source.items():
            if value is not None and isinstance(value, (str, int, float, bool, list, dict)):
                payload[key] = value
            elif value is not None:
                payload[key] = str(value)
        for key in ("tenant_id", "server_id", "agent_id", "connection_id", "server_ip"):
            if source.get(key) not in (None, ""):
                payload[key] = str(source[key])
        payload["updated_monotonic"] = monotonic()
        tenant_id = str(payload.get("tenant_id") or "")
        server_id = str(payload.get("server_id") or "")
        agent_id = str(payload.get("agent_id") or "")
        if not tenant_id or not server_id or not agent_id:
            return
        client = cls.redis_client()
        if client:
            encoded = json.dumps(payload, separators=(",", ":"), default=str)
            pipe = client.pipeline()
            pipe.setex(cls._server_key(tenant_id, server_id), cls._ttl(), encoded)
            pipe.setex(cls._agent_key(tenant_id, agent_id), cls._ttl(), encoded)
            pipe.execute()
            return
        with cls._lock:
            cls._memory[cls._server_key(tenant_id, server_id)] = payload
            cls._memory[cls._agent_key(tenant_id, agent_id)] = payload

    @classmethod
    def heartbeat(cls, info):
        cls.register(info)

    @classmethod
    def _get(cls, key):
        client = cls.redis_client()
        if client:
            value = client.get(key)
            return json.loads(value) if value else None
        with cls._lock:
            value = cls._memory.get(key)
            if not value:
                return None
            if monotonic() - float(value.get("updated_monotonic") or 0) > cls._ttl():
                cls._memory.pop(key, None)
                return None
            return dict(value)

    @classmethod
    def get_server(cls, tenant_id, server_id):
        return cls._get(cls._server_key(str(tenant_id), str(server_id)))

    @classmethod
    def get_agent(cls, tenant_id, agent_id):
        return cls._get(cls._agent_key(str(tenant_id), str(agent_id)))

    @classmethod
    def remove(cls, info):
        info = info or {}
        tenant_id = str(info.get("tenant_id") or "")
        server_id = str(info.get("server_id") or "")
        agent_id = str(info.get("agent_id") or "")
        keys = [
            cls._server_key(tenant_id, server_id),
            cls._agent_key(tenant_id, agent_id),
        ]
        client = cls.redis_client()
        if client:
            current = cls.get_server(tenant_id, server_id)
            if current and str(current.get("connection_id")) == str(info.get("connection_id")):
                client.delete(*keys)
            return
        with cls._lock:
            for key in keys:
                current = cls._memory.get(key)
                if current and str(current.get("connection_id")) == str(info.get("connection_id")):
                    cls._memory.pop(key, None)

    @classmethod
    def online_count(cls):
        client = cls.redis_client()
        if client:
            return sum(1 for _ in client.scan_iter(f"{cls.PREFIX}:server:*", count=500))
        with cls._lock:
            return sum(1 for key in cls._memory if ":server:" in key)
