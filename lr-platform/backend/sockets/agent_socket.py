from typing import Any, cast
from threading import Lock
from time import monotonic

from flask import has_request_context, request
from flask_socketio import disconnect, join_room
from backend.extensions import socketio
from backend.manager.agent_manager import register_agent, set_offline, update_heartbeat
from backend.manager.logger import get_logger
from backend.manager.stream_manager import remove_sid
from backend.services.agent_enrollment_service import AgentEnrollmentService
from backend.services.agent_command_service import AgentCommandService
from backend.services.agent_presence_service import AgentPresenceService

connected_agents = {}
logger = get_logger(__name__)
_SHORTCUT_RETRY_INTERVAL_SECONDS = 30
_shortcut_retry_last_at = {}
_shortcut_retry_inflight = set()
_shortcut_retry_lock = Lock()


def _request_sid():
    return str(getattr(cast(Any, request), 'sid', ''))


def get_agent_sid(agent_id, tenant_id=None):
    for sid, info in connected_agents.items():
        if info.get("agent_id") == agent_id and (
            tenant_id is None or str(info.get("tenant_id")) == str(tenant_id)
        ):
            return sid
    return None


def _run_pending_shortcut_sync(agent_sid, reconcile_assignments):
    try:
        from backend.services.desktop_shortcut_service import DesktopShortcutService

        DesktopShortcutService.sync_pending_for_agent(
            agent_sid,
            reconcile_assignments=reconcile_assignments,
        )
    except Exception as error:
        logger.warning("Pending desktop shortcut sync failed: %s", error)
    finally:
        with _shortcut_retry_lock:
            _shortcut_retry_inflight.discard(agent_sid)


def _schedule_pending_shortcut_sync(
    agent_sid,
    agent_id,
    *,
    force=False,
    reconcile_assignments=False,
):
    now = monotonic()
    with _shortcut_retry_lock:
        last_at = _shortcut_retry_last_at.get(agent_id, 0)
        if agent_sid in _shortcut_retry_inflight:
            return False
        if not force and now - last_at < _SHORTCUT_RETRY_INTERVAL_SECONDS:
            return False
        _shortcut_retry_last_at[agent_id] = now
        _shortcut_retry_inflight.add(agent_sid)

    try:
        socketio.start_background_task(
            _run_pending_shortcut_sync,
            agent_sid,
            reconcile_assignments,
        )
    except Exception:
        with _shortcut_retry_lock:
            _shortcut_retry_inflight.discard(agent_sid)
        raise
    return True


def register_socket_events(socketio_instance=None):
    """Import hook used by sockets.socket_handler.

    The event handlers in this module are registered by the decorators below
    when the module is imported.
    """
    return None

@socketio.on("agent_connect", namespace='/agent')
def handle_agent_connect(data):
    data = data or {}
    agent_id = data.get("agent_id")
    if agent_id:
        identity = AgentEnrollmentService.authenticate_or_enroll(data)
        if not identity:
            logger.warning("Rejected unenrolled agent: %s", agent_id)
            disconnect(namespace="/agent")
            return {"success": False, "message": "Valid agent enrollment is required"}
        tenant_id = identity.get("tenant_id")
        server_id = identity.get("server_id")
        register_agent(
            agent_id=agent_id,
            hostname=data.get("hostname"),
            ip_address=data.get("ip_address"),
            username=data.get("username"),
            os=data.get("os"),
            cpu=data.get("cpu"),
            ram=data.get("ram"),
            tenant_id=tenant_id,
            server_id=server_id,
        )
        connected_agents[_request_sid()] = {
            "agent_id": agent_id,
            "hostname": data.get("hostname"),
            "ip_address": data.get("ip_address"),
            "username": data.get("username"),
            "os": data.get("os"),
            "cpu": data.get("cpu"),
            "ram": data.get("ram"),
            "status": "online",
            "tenant_id": tenant_id,
            "server_id": server_id,
            "server_ip": identity.get("server_ip"),
            "connection_id": _request_sid(),
        }
        AgentPresenceService.register(connected_agents[_request_sid()])
        if tenant_id is not None:
            join_room(f"tenant:{tenant_id}", namespace="/agent")
            join_room(f"server:{server_id}", namespace="/agent")
            join_room(f"agent:{tenant_id}:{agent_id}", namespace="/agent")
        logger.info("Agent connected: %s", agent_id)
        try:
            _schedule_pending_shortcut_sync(
                _request_sid(),
                agent_id,
                force=True,
                reconcile_assignments=True,
            )
        except Exception as error:
            logger.warning("Pending desktop shortcut sync did not start: %s", error)
        try:
            from backend.services.remote_app_service import RemoteAppService

            socketio.start_background_task(
                RemoteAppService.sync_pending_for_agent,
                _request_sid(),
            )
        except Exception as error:
            logger.warning("Pending RemoteApp sync did not start: %s", error)
        return {
            "success": True,
            "agent_id": agent_id,
            "tenant_id": str(tenant_id) if tenant_id else None,
            "server_id": str(server_id) if server_id else None,
            "agent_credential": identity.get("new_credential"),
        }
    else:
        logger.warning("Agent connected without an ID")
        return {"success": False, "message": "agent_id is required"}

@socketio.on("disconnect", namespace='/agent')
def handle_agent_disconnect():
    sid = _request_sid()
    agent_info = connected_agents.pop(sid, None)
    for agent_id in remove_sid(sid):
        logger.info("Stream closed: %s", agent_id)
    if agent_info:
        AgentPresenceService.remove(agent_info)
        active_presence = AgentPresenceService.get_server(
            agent_info.get("tenant_id"),
            agent_info.get("server_id"),
        )
        if not active_presence:
            set_offline(agent_info["agent_id"], agent_info.get("tenant_id"))
        logger.info("Agent disconnected: %s", agent_info["agent_id"])
    else:
        logger.warning("Agent disconnected without a known ID")

@socketio.on("heartbeat", namespace='/agent')
def handle_heartbeat(data):
    data = data or {}
    agent_id = data.get("agent_id")
    if not agent_id:
        return
    identity = connected_agents.get(_request_sid()) if has_request_context() else None
    if identity is None:
        identity = next(
            (item for item in connected_agents.values() if item.get("agent_id") == agent_id),
            None,
        )
    if identity is None:
        return
    try:
        AgentPresenceService.heartbeat(identity)
        if identity.get("tenant_id") is None:
            update_heartbeat(agent_id)
        else:
            update_heartbeat(agent_id, identity.get("tenant_id"))
    except Exception as error:
        logger.warning("Heartbeat persistence failed for %s: %s", agent_id, error)

    for sid, info in connected_agents.items():
        if info["agent_id"] == agent_id:
            connected_agents[sid]["status"] = "online"
            logger.debug("Heartbeat received from %s", agent_id)
            try:
                _schedule_pending_shortcut_sync(sid, agent_id)
            except Exception as error:
                logger.warning("Pending desktop shortcut retry did not start: %s", error)
            break


@socketio.on("agent_command_result", namespace="/agent")
def handle_agent_command_result(data):
    data = data or {}
    identity = connected_agents.get(_request_sid())
    if not identity:
        return {"success": False, "message": "Unknown Agent connection"}
    if str(data.get("agent_id") or "") != str(identity.get("agent_id") or ""):
        return {"success": False, "message": "Agent identity mismatch"}
    AgentCommandService.publish_result(
        data.get("request_id"),
        data.get("result") if isinstance(data.get("result"), dict) else {
            "success": False,
            "message": "Agent returned an invalid command result.",
        },
    )
    return {"success": True}
