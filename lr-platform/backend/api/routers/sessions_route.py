from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from backend.services.sessions_service import SessionsService


sessions_bp = Blueprint(
    "sessions",
    __name__,
    url_prefix="/api/sessions"
)


@sessions_bp.route("/", methods=["GET"])
@login_required
def list_sessions():
    result, status_code = SessionsService.list_sessions(
        request.args,
        current_user,
    )

    return jsonify(result), status_code


@sessions_bp.route("/stats", methods=["GET"])
@login_required
def get_stats():
    result, status_code = SessionsService.get_stats(current_user)
    return jsonify(result), status_code


@sessions_bp.route("/<session_id>", methods=["GET"])
@login_required
def get_session(session_id):
    result, status_code = SessionsService.get_session(
        session_id,
        current_user,
    )

    return jsonify(result), status_code


@sessions_bp.route("/me", methods=["GET"])
@login_required
def my_sessions():
    result, status_code = SessionsService.get_my_sessions(
        current_user.id
    )

    return jsonify(result), status_code


@sessions_bp.route("/launch", methods=["POST"])
@login_required
def launch_session():
    result, status_code = SessionsService.launch_session(
        data=request.get_json(silent=True) or {},
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent")
    )

    return jsonify(result), status_code


@sessions_bp.route(
    "/<session_id>/kill",
    methods=["DELETE", "POST"]
)
@login_required
def kill_session(session_id):
    result, status_code = SessionsService.kill_session(
        session_id=session_id,
        user_id=current_user.id,
        ip_address=request.remote_addr
    )

    return jsonify(result), status_code


@sessions_bp.route("/<session_id>/ping", methods=["POST"])
@login_required
def ping_session(session_id):
    result, status_code = SessionsService.ping_session(
        session_id,
        current_user,
    )

    return jsonify(result), status_code


@sessions_bp.route("/<session_id>/reconnect", methods=["POST"])
@login_required
def reconnect_session(session_id):
    result, status_code = SessionsService.reconnect_session(
        session_id=session_id,
        user=current_user,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    )

    return jsonify(result), status_code
