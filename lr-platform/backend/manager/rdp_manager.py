import logging
import socket
import threading
import time
import uuid
from datetime import datetime
from typing import Any

from flask import current_app

from backend.security.credential_crypto import decrypt_secret

logger = logging.getLogger(__name__)


def _utcnow():
    return datetime.utcnow()


def _as_bool(value: Any, default: bool | None = True) -> bool | None:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_text(value):
    return str(value or "").strip()


class RDPSession:
    def __init__(self, config, client_sid=None):
        self.id = str(uuid.uuid4())
        self.config = self._normalize_config(config)
        self.client_sid = client_sid
        self.status = "created"
        self.backend_type = None
        self.error = None
        self.connection_id = None
        self.launch_url = None
        self.guac_token = None
        self.guac_config = None
        self.created_at = _utcnow()
        self.started_at = None
        self.last_seen_at = self.created_at
        self.closed_at = None
        self.input_events = 0
        self.resize_events = 0
        self.width = self.config["width"]
        self.height = self.config["height"]
        self.lock = threading.RLock()

    def _normalize_config(self, config):
        config = config or {}
        host = _clean_text(config.get("host") or config.get("hostname") or config.get("ip_address"))
        if not host:
            raise ValueError("RDP host is required")

        options = config.get("options") or {}
        app = config.get("app") or config.get("application")

        return {
            "name": _clean_text(config.get("name") or config.get("server_name") or host),
            "host": host,
            "port": _as_int(config.get("port") or config.get("rdp_port"), 3389),
            "username": _clean_text(config.get("username") or config.get("rdp_username")),
            "password": decrypt_secret(config.get("password") or config.get("rdp_password")),
            "domain": _clean_text(config.get("domain")),
            "security": _clean_text(config.get("security") or "any"),
            "ignore_cert": _as_bool(config.get("ignore_cert"), True),
            "width": _as_int(config.get("width") or options.get("width"), 1280),
            "height": _as_int(config.get("height") or options.get("height"), 720),
            "app": app if isinstance(app, dict) else None,
            "precheck": _as_bool(config.get("precheck"), None),
        }

    def start(self):
        with self.lock:
            if self.status in {"active", "starting"}:
                return self.to_dict()
            self.status = "starting"
            self.error = None

        try:
            if self._precheck_enabled():
                self._check_rdp_port()

            self._start_guacamole_session()
            with self.lock:
                self.status = "active"
                self.backend_type = "guacamole"
                self.started_at = _utcnow()
                self.last_seen_at = self.started_at
            logger.info("Started RDP session %s for %s", self.id, self.config["host"])
            return self.to_dict()
        except Exception as error:
            with self.lock:
                self.status = "error"
                self.error = str(error)
            logger.exception("Failed to start RDP session %s", self.id)
            raise

    def _precheck_enabled(self):
        configured = current_app.config.get("RDP_PRECHECK_ENABLED", "true")
        if self.config["precheck"] is not None:
            return self.config["precheck"]
        return _as_bool(configured, True)

    def _check_rdp_port(self):
        timeout = float(current_app.config.get("RDP_PRECHECK_TIMEOUT", 3) or 3)
        with socket.create_connection((self.config["host"], self.config["port"]), timeout=timeout):
            return True

    def _start_guacamole_session(self):
        if not all(
            current_app.config.get(key)
            for key in ("GUACAMOLE_URL", "GUACAMOLE_USER", "GUACAMOLE_PASSWORD")
        ):
            raise RuntimeError(
                "Remote desktop gateway is not configured. "
                "Set GUACAMOLE_URL, GUACAMOLE_USER, and GUACAMOLE_PASSWORD."
            )

        from backend.manager.guacamole_manager import GuacamoleClient

        self.guac_config = {
            "base_url": current_app.config["GUACAMOLE_URL"],
            "username": current_app.config["GUACAMOLE_USER"],
            "password": current_app.config["GUACAMOLE_PASSWORD"],
            "public_url": current_app.config.get("GUACAMOLE_PUBLIC_URL"),
            "data_source": current_app.config.get("GUACAMOLE_DATA_SOURCE", "default"),
        }
        client = GuacamoleClient(**self.guac_config)
        result = client.create_rdp_connection(
            name=self.config["name"],
            host=self.config["host"],
            port=self.config["port"],
            rdp_username=self.config["username"],
            rdp_password=self.config["password"],
            domain=self.config["domain"],
            security=self.config["security"],
            ignore_cert=self.config["ignore_cert"],
            app=self.config["app"],
        )
        if not result.get("success"):
            raise RuntimeError(result.get("error") or "Could not create Guacamole RDP connection")

        self.connection_id = result.get("connection_id")
        self.launch_url = result.get("client_url")
        self.guac_token = result.get("token")

    def send_input(self, event):
        with self.lock:
            self._ensure_active()
            self.input_events += 1
            self.last_seen_at = _utcnow()

        event = event or {}
        event_type = event.get("type") or event.get("action")
        logger.debug("RDP session %s input event: %s", self.id, event_type)
        return {
            "success": True,
            "session_id": self.id,
            "handled_by": self.backend_type,
            "message": (
                "Input is handled by the Guacamole browser tunnel for this RDP session. "
                "Backend event was accepted and recorded."
            ),
        }

    def resize(self, width, height):
        width = max(320, min(7680, _as_int(width, self.width)))
        height = max(240, min(4320, _as_int(height, self.height)))
        with self.lock:
            self._ensure_active()
            self.width = width
            self.height = height
            self.resize_events += 1
            self.last_seen_at = _utcnow()

        logger.info("RDP session %s resized to %sx%s", self.id, width, height)
        return {
            "success": True,
            "session_id": self.id,
            "width": width,
            "height": height,
            "message": "Resize accepted. Guacamole uses display-update resize handling.",
        }

    def close(self):
        with self.lock:
            if self.status == "closed":
                return self.to_dict()
            connection_id = self.connection_id
            self.status = "closing"

        if connection_id:
            try:
                from backend.manager.guacamole_manager import GuacamoleClient

                if self.guac_config:
                    GuacamoleClient(**self.guac_config).delete_connection(connection_id)
            except Exception:
                logger.exception("Failed to delete Guacamole connection %s", connection_id)

        with self.lock:
            self.status = "closed"
            self.closed_at = _utcnow()
            self.last_seen_at = self.closed_at
        logger.info("Closed RDP session %s", self.id)
        return self.to_dict()

    def _ensure_active(self):
        if self.status != "active":
            raise RuntimeError(f"RDP session is not active: {self.status}")

    def is_expired(self, now=None, idle_seconds=1800, max_age_seconds=14400):
        now = now or _utcnow()
        with self.lock:
            if self.status in {"closed", "error"}:
                return True
            if (now - self.last_seen_at).total_seconds() > idle_seconds:
                return True
            if (now - self.created_at).total_seconds() > max_age_seconds:
                return True
            return False

    def to_dict(self):
        with self.lock:
            return {
                "id": self.id,
                "session_id": self.id,
                "status": self.status,
                "backend": self.backend_type,
                "host": self.config["host"],
                "port": self.config["port"],
                "name": self.config["name"],
                "width": self.width,
                "height": self.height,
                "connection_id": self.connection_id,
                "launch_url": self.launch_url,
                "error": self.error,
                "input_events": self.input_events,
                "resize_events": self.resize_events,
                "created_at": self.created_at.isoformat(),
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "last_seen_at": self.last_seen_at.isoformat(),
                "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            }


class RDPManager:
    def __init__(self, cleanup_interval_seconds=60):
        self.sessions: dict[str, RDPSession] = {}
        self.lock = threading.RLock()
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self._cleanup_started = False

    def create_session(self, config, client_sid=None):
        self._ensure_cleanup_thread()
        session = RDPSession(config, client_sid=client_sid)
        with self.lock:
            self.sessions[session.id] = session
        try:
            session.start()
        except Exception:
            with self.lock:
                self.sessions.pop(session.id, None)
            raise
        return session.id

    def create_session_info(self, config, client_sid=None):
        session_id = self.create_session(config, client_sid=client_sid)
        return self.get_session(session_id).to_dict()

    def get_session(self, session_id):
        with self.lock:
            session = self.sessions.get(session_id)
        if not session:
            raise RuntimeError("Session not found")
        return session

    def status(self, session_id=None):
        if session_id:
            return self.get_session(session_id).to_dict()
        with self.lock:
            return [session.to_dict() for session in self.sessions.values()]

    def send_input(self, session_id, event):
        return self.get_session(session_id).send_input(event)

    def resize(self, session_id, width, height):
        return self.get_session(session_id).resize(width, height)

    def close_session(self, session_id):
        with self.lock:
            session = self.sessions.pop(session_id, None)
        if not session:
            return {"success": False, "error": "Session not found", "session_id": session_id}
        data = session.close()
        data["success"] = True
        return data

    def close_sessions_for_sid(self, client_sid):
        closed = []
        with self.lock:
            session_ids = [
                session_id
                for session_id, session in self.sessions.items()
                if session.client_sid == client_sid
            ]
        for session_id in session_ids:
            closed.append(self.close_session(session_id))
        return closed

    def cleanup_stale_sessions(self, idle_seconds=1800, max_age_seconds=14400):
        now = _utcnow()
        with self.lock:
            session_ids = [
                session_id
                for session_id, session in self.sessions.items()
                if session.is_expired(now, idle_seconds=idle_seconds, max_age_seconds=max_age_seconds)
            ]
        for session_id in session_ids:
            logger.info("Cleaning stale RDP session %s", session_id)
            self.close_session(session_id)
        return session_ids

    def _ensure_cleanup_thread(self):
        with self.lock:
            if self._cleanup_started:
                return
            self._cleanup_started = True

        thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        thread.start()

    def _cleanup_loop(self):
        while True:
            time.sleep(self.cleanup_interval_seconds)
            try:
                self.cleanup_stale_sessions()
            except Exception:
                logger.exception("RDP cleanup loop failed")


rdp_manager = RDPManager()
