from flask import Blueprint, Response, jsonify, redirect, request
from flask_login import current_user, login_required

from backend.services.lr_resources_service import LrResourcesService
from backend.services.portal_service import PortalService
from backend.services.user_license_service import UserLicenseService


lr_bp = Blueprint("lr", __name__, url_prefix="/api/lr")


def _license_gate(context):
    blocked = UserLicenseService.block_response(current_user, context=context)
    if blocked:
        result, status_code = blocked
        return jsonify(result), 403 if status_code == 402 else status_code
    return None


@lr_bp.route("/my-resources", methods=["GET"])
@login_required
def my_resources():
    result, status_code = LrResourcesService.my_resources(current_user.id)
    return jsonify(result), status_code


@lr_bp.route("/launch", methods=["POST"])
@login_required
def launch_resource():
    data = request.get_json(silent=True) or {}
    if not current_user.is_active:
        return jsonify({"success": False, "error": "User is disabled"}), 403
    data["connection_type"] = "remoteapp"
    blocked = _license_gate({
        "action": "launch_resource",
        "resource_id": str(data.get("resource_id") or ""),
        "type": str(data.get("type") or ""),
    })
    if blocked:
        return blocked

    result, status_code = LrResourcesService.launch_resource(
        data=data,
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    )
    return jsonify(result), status_code


@lr_bp.route("/desktop", methods=["POST"])
@login_required
def launch_desktop():
    if not current_user.is_active:
        return jsonify({"success": False, "error": "User is disabled"}), 403
    blocked = _license_gate({"action": "launch_native_desktop"})
    if blocked:
        return blocked

    result, status_code = LrResourcesService.launch_assigned_native_desktop(
        user=current_user,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent"),
    )
    return jsonify(result), status_code


@lr_bp.route("/sessions/<session_id>/file.rdp", methods=["GET"])
@login_required
def native_remote_app_file(session_id):
    if not current_user.is_active:
        return jsonify({"success": False, "error": "User is disabled"}), 403
    blocked = UserLicenseService.block_response(current_user, context={
        "action": "download_remote_app_rdp",
        "session_id": str(session_id),
    })
    if blocked:
        result, _ = blocked
        return jsonify({
            "success": False,
            "error": result.get("error") or result.get("message") or "RemoteApp license is required",
        }), 403

    result, error, status_code = PortalService.get_rdp_file(
        session_id=session_id,
        user_id=current_user.id,
        require_native=True,
        consume_native=True,
    )
    if error:
        return jsonify({"success": False, "error": error}), status_code
    if result is None:
        return jsonify({
            "success": False,
            "error": "RemoteApp file could not be generated",
        }), 500

    return Response(
        result["content"],
        content_type="application/x-rdp",
        headers={
            "Content-Disposition": f'attachment; filename="{result["filename"]}"',
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


@lr_bp.route("/sessions/<session_id>/open", methods=["GET"])
@login_required
def open_browser_remote_app(session_id):
    if not current_user.is_active:
        return jsonify({"success": False, "error": "User is disabled"}), 403
    blocked = _license_gate({
        "action": "open_browser_remote_app",
        "session_id": str(session_id),
    })
    if blocked:
        return blocked

    result, status_code = PortalService.consume_browser_remote_app_launch(
        session_id=session_id,
        ticket=str(request.args.get("ticket") or ""),
        user=current_user,
    )
    if status_code != 200:
        return jsonify(result), status_code

    response = redirect(result["redirect_url"], code=302)
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
