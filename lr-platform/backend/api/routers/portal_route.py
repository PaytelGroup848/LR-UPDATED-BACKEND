import os

from flask import Blueprint, Response, render_template, request, jsonify, send_file
from flask_login import login_required, current_user
from jinja2 import TemplateNotFound

from backend.api.routers.auth_route import admin_required
from backend.services.app_update_service import AppUpdateService
from backend.services.portal_service import PortalService
from backend.services.user_license_service import UserLicenseService


portal_bp = Blueprint(
    "portal",
    __name__,
    url_prefix="/portal"
)


@portal_bp.route("/", methods=["GET"])
@login_required
def portal_home():
    apps, _ = PortalService.get_portal_apps(current_user.id)
    sessions, _ = PortalService.get_my_sessions(current_user.id)
    stats, _ = PortalService.get_session_stats(current_user.id)

    payload = {
        "success": True,
        "user": PortalService.get_current_user(current_user),
        "servers": PortalService.get_home_servers(),
        "apps": apps.get("apps", []),
        "sessions": sessions.get("sessions", []),
        "stats": stats,
    }

    try:
        return render_template(
            "portal.html",
            user=current_user,
            servers=payload["servers"],
            apps=payload["apps"],
            sessions=payload["sessions"],
            stats=payload["stats"],
        )
    except TemplateNotFound:
        return jsonify(payload), 200


@portal_bp.route("/dashboard", methods=["GET"])
@admin_required
def dashboard():
    data = PortalService.get_dashboard_data()

    try:
        return render_template(
            "dashboard.html",
            user=current_user,
            stats=data["stats"],
            servers=data["servers"],
        )
    except TemplateNotFound:
        return jsonify({
            "success": True,
            "user": PortalService.get_current_user(current_user),
            **data,
        }), 200


@portal_bp.route("/api/me", methods=["GET"])
@login_required
def portal_me():
    return jsonify(PortalService.get_current_user(current_user)), 200


@portal_bp.route("/api/servers", methods=["GET"])
@login_required
def get_portal_servers():
    result, status_code = PortalService.get_portal_servers()
    return jsonify(result), status_code


@portal_bp.route("/api/apps", methods=["GET"])
@login_required
def get_portal_apps():
    result, status_code = PortalService.get_portal_apps(
        current_user.id
    )

    return jsonify(result), status_code


def _license_gate(context):
    blocked = UserLicenseService.block_response(current_user, context=context)
    if blocked:
        result, status_code = blocked
        return jsonify(result), status_code
    return None


@portal_bp.route("/api/apps/<app_id>/launch", methods=["POST"])
@login_required
def portal_launch_app(app_id):
    blocked = _license_gate({"action": "launch_app", "app_id": str(app_id)})
    if blocked:
        return blocked

    result, status_code = PortalService.launch_app(
        app_id=app_id,
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
        data=request.get_json(silent=True) or {},
    )

    return jsonify(result), status_code


@portal_bp.route("/api/apps/<app_id>/launch-remote-app", methods=["POST"])
@login_required
def portal_launch_native_remote_app(app_id):
    blocked = _license_gate({"action": "launch_remote_app", "app_id": str(app_id)})
    if blocked:
        return blocked

    result, status_code = PortalService.launch_native_remote_app(
        app_id=app_id,
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    )
    return jsonify(result), status_code


@portal_bp.route("/api/launch", methods=["POST"])
@login_required
def portal_launch():
    blocked = _license_gate({"action": "launch_server"})
    if blocked:
        return blocked

    result, status_code = PortalService.launch_server(
        data=request.get_json(silent=True) or {},
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    )

    return jsonify(result), status_code


@portal_bp.route("/api/my-sessions", methods=["GET"])
@login_required
def my_sessions():
    result, status_code = PortalService.get_my_sessions(
        current_user.id
    )

    return jsonify(result), status_code


@portal_bp.route("/api/sessions/stats", methods=["GET"])
@login_required
def sessions_stats():
    result, status_code = PortalService.get_session_stats(
        current_user.id
    )

    return jsonify(result), status_code


@portal_bp.route("/api/sessions/<session_id>/rdp-file", methods=["GET"])
@login_required
def session_rdp_file(session_id):
    blocked = _license_gate({"action": "download_rdp", "session_id": str(session_id)})
    if blocked:
        return blocked

    result, error, status_code = PortalService.get_rdp_file(
        session_id=session_id,
        user_id=current_user.id,
    )
    if error:
        return jsonify({
            "success": False,
            "error": error,
        }), status_code
    if result is None:
        return jsonify({
            "success": False,
            "error": "RDP file could not be generated",
        }), 500

    return Response(
        result["content"],
        mimetype="application/x-rdp",
        headers={
            "Content-Disposition": f'attachment; filename="{result["filename"]}"'
        },
    )


@portal_bp.route("/api/sessions/<session_id>/reconnect", methods=["POST"])
@login_required
def reconnect_portal_session(session_id):
    blocked = _license_gate({"action": "reconnect_session", "session_id": str(session_id)})
    if blocked:
        return blocked

    result, status_code = PortalService.reconnect_session(
        session_id=session_id,
        user=current_user,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    )
    return jsonify(result), status_code


@portal_bp.route("/api/download-client", methods=["GET"])
def download_client():
    exe_path = PortalService.get_client_exe_path()

    if not os.path.exists(exe_path):
        return jsonify({
            "success": False,
            "error": "Client not found"
        }), 404

    return send_file(
        exe_path,
        as_attachment=True,
        download_name="lr_remote_access_client.exe",
    )


@portal_bp.route("/api/download-admin-panel", methods=["GET"])
def download_admin_panel():
    exe_path = PortalService.get_admin_panel_exe_path()

    if not os.path.exists(exe_path):
        return jsonify({
            "success": False,
            "error": "Admin Panel app not found"
        }), 404

    return send_file(
        exe_path,
        as_attachment=True,
        download_name="Admin Panel.exe",
    )


@portal_bp.route("/api/download-updater", methods=["GET"])
def download_updater():
    result = AppUpdateService.get_updater_download()

    if not result["success"]:
        return jsonify(result), 404

    return send_file(
        result["file_path"],
        as_attachment=True,
        download_name=result.get("download_name", "LR Updater.exe"),
    )


@portal_bp.route("/api/app-updates/<app_id>", methods=["GET"])
def portal_app_update_info(app_id):
    result, status_code = AppUpdateService.get_update_info(
        app_id=app_id,
        current_version=request.args.get("current_version"),
    )
    return jsonify(result), status_code
