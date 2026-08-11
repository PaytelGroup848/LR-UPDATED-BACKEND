from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from backend.api.routers.auth_route import admin_required
from backend.services.agent_enrollment_service import AgentEnrollmentService
from backend.services.agent_service import AgentService
from backend.extensions import socketio


agent_bp = Blueprint("agent", __name__)


@agent_bp.route(
    "/agents",
    methods=["GET"]
)
@login_required
def get_agents():

    return jsonify(
        AgentService.get_agents(current_user, username=request.args.get("username"))
    )


@agent_bp.route(
    "/agents/<agent_id>",
    methods=["GET"]
)
@login_required
def get_agent(agent_id):

    result = AgentService.get_agent(
        agent_id, current_user
    )

    if not result["success"]:
        return jsonify(result), 404

    return jsonify(result)


@agent_bp.post("/servers/<server_id>/agent-enrollment-token")
@admin_required
def create_enrollment_token(server_id):
    try:
        data = request.get_json(silent=True) or {}
        result = AgentEnrollmentService.issue(
            current_user,
            server_id,
            machine_claim=data.get("machine") or data,
        )
        return jsonify({"success": True, **result}), 201
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 404


@agent_bp.delete("/servers/<server_id>/agent-binding")
@admin_required
def revoke_agent_binding(server_id):
    try:
        result = AgentEnrollmentService.revoke(current_user, server_id)
        socketio.emit(
            "agent_binding_revoked",
            {"server_id": server_id},
            namespace="/agent",
            to=f"server:{server_id}",
        )
        return jsonify(result), 200
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 404
