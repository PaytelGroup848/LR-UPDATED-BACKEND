from typing import Any, cast

from flask import request
from flask_socketio import Namespace, emit, join_room, leave_room

from backend.manager.rdp_manager import rdp_manager


def _request_sid():
    return str(getattr(cast(Any, request), "sid", ""))


class RDPNamespace(Namespace):
    def on_connect(self):
        emit("connected", {"message": "RDP gateway connected"})

    def on_disconnect(self):
        rdp_manager.close_sessions_for_sid(_request_sid())

    def on_rdp_connect(self, data):
        """Start an RDP session.

        Expected data:
        {
            "host": "...",
            "port": 3389,
            "username": "...",
            "password": "...",
            "width": 1280,
            "height": 720,
            "app": {... optional RemoteApp config ...}
        }
        """
        try:
            session = rdp_manager.create_session_info(data or {}, client_sid=_request_sid())
            join_room(session["session_id"])
            emit("rdp_connected", session)
        except Exception as error:
            emit("rdp_error", {"error": str(error)})

    def on_rdp_input(self, data):
        data = data or {}
        try:
            result = rdp_manager.send_input(data.get("session_id"), data.get("event") or data)
            emit("rdp_input_result", result)
        except Exception as error:
            emit("rdp_error", {"error": str(error), "session_id": data.get("session_id")})

    def on_rdp_resize(self, data):
        data = data or {}
        try:
            result = rdp_manager.resize(
                data.get("session_id"),
                data.get("width"),
                data.get("height"),
            )
            emit("rdp_resize_result", result)
        except Exception as error:
            emit("rdp_error", {"error": str(error), "session_id": data.get("session_id")})

    def on_rdp_disconnect(self, data):
        data = data or {}
        session_id = data.get("session_id")
        try:
            result = rdp_manager.close_session(session_id)
            if session_id:
                leave_room(session_id)
            emit("rdp_disconnected", result)
        except Exception as error:
            emit("rdp_error", {"error": str(error), "session_id": session_id})

    def on_rdp_status(self, data=None):
        data = data or {}
        try:
            emit("rdp_status", {"success": True, "sessions": rdp_manager.status(data.get("session_id"))})
        except Exception as error:
            emit("rdp_error", {"error": str(error), "session_id": data.get("session_id")})


def init_rdp_namespace(socketio):
    socketio.on_namespace(RDPNamespace("/rdp"))
