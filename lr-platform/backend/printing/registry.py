from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PrintClientRegistration:
    session_id: str
    connection_id: str
    user_id: str
    tenant_id: Optional[str] = None
    client_type: str = "desktop"
    capabilities: dict[str, Any] = field(default_factory=dict)
    printers: list[str] = field(default_factory=list)
    registered_at: datetime = field(default_factory=_utcnow)
    last_seen_at: datetime = field(default_factory=_utcnow)

    def metadata(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "connection_id": self.connection_id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "client_type": self.client_type,
            "capabilities": dict(self.capabilities),
            "printers": list(self.printers),
            "registered_at": self.registered_at.isoformat(),
            "last_seen_at": self.last_seen_at.isoformat(),
        }


class SessionRegistry:
    """Thread-safe exact-session registry for print-capable clients."""

    def __init__(self) -> None:
        self._clients: dict[tuple[str, str, str], PrintClientRegistration] = {}
        self._lock = threading.RLock()

    def register_print_client(
        self,
        session_id: str,
        connection_id: str,
        user_id: str,
        client: Optional[Any] = None,
        *,
        client_type: str = "desktop",
        capabilities: Optional[dict[str, Any]] = None,
        printers: Optional[list[str]] = None,
        tenant_id: Optional[str] = None,
    ) -> PrintClientRegistration:
        del client  
        registration = PrintClientRegistration(
            session_id=str(session_id),
            connection_id=str(connection_id),
            user_id=str(user_id),
            tenant_id=str(tenant_id or ""),
            client_type=client_type,
            capabilities=dict(capabilities or {}),
            printers=list(printers or []),
        )
        with self._lock:
            self._clients[(registration.tenant_id or "", registration.session_id, registration.connection_id)] = registration
        return registration

    def unregister_print_client(self, session_id: str, connection_id: str, tenant_id: Optional[str] = None) -> bool:
        with self._lock:
            return self._clients.pop((str(tenant_id or ""), str(session_id), str(connection_id)), None) is not None

    def heartbeat(self, session_id: str, connection_id: str, user_id: str, tenant_id: Optional[str] = None) -> bool:
        with self._lock:
            client = self._clients.get((str(tenant_id or ""), str(session_id), str(connection_id)))
            if not client or client.user_id != str(user_id):
                return False
            client.last_seen_at = _utcnow()
            return True

    def get_print_client(
        self,
        session_id: str,
        connection_id: Optional[str] = None,
        *,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> Optional[PrintClientRegistration]:
        with self._lock:
            if connection_id:
                client = self._clients.get((str(tenant_id or ""), str(session_id), str(connection_id)))
                if client and (user_id is None or client.user_id == str(user_id)):
                    return client
                return None
            matches = [
                client for (registered_tenant, registered_session, _), client in self._clients.items()
                if registered_session == str(session_id)
                and registered_tenant == str(tenant_id or "")
                and (user_id is None or client.user_id == str(user_id))
            ]
            return matches[0] if len(matches) == 1 else None

    def count_for_session(self, session_id: str, user_id: str, tenant_id: Optional[str] = None) -> int:
        with self._lock:
            return sum(
                1 for client in self._clients.values()
                if client.session_id == str(session_id) and client.user_id == str(user_id)
                and client.tenant_id == str(tenant_id or "")
            )

    def list_clients(self, tenant_id: Optional[str] = None) -> list[dict[str, Any]]:
        with self._lock:
            return [
                client.metadata() for client in self._clients.values()
                if tenant_id is None or client.tenant_id == str(tenant_id)
            ]

    def remove_stale(self, cutoff: datetime) -> list[PrintClientRegistration]:
        removed: list[PrintClientRegistration] = []
        with self._lock:
            for key, client in list(self._clients.items()):
                if client.last_seen_at < cutoff:
                    removed.append(self._clients.pop(key))
        return removed
