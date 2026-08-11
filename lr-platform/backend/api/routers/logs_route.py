from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from backend.services.logs_service import ActivityLogService


logs = Blueprint("logs", __name__)


@logs.route("/logs", methods=["GET"])
@login_required
def get_logs():

    if not current_user.has_role("Admin"):
        return jsonify({
            "message": "Forbidden"
        }), 403

    return jsonify(
        ActivityLogService.get_logs(
            request.args.get("limit", 100, type=int),
            user_id=request.args.get("user_id"),
            tenant_id=current_user.get("tenant_id"),
        )
    ), 200
