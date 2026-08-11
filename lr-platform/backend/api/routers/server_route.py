from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required

from backend.api.routers.auth_route import admin_required
from backend.services.server_service import ServerService


server = Blueprint("server", __name__)


@server.route("/update-server/<id>", methods=["POST"])
@admin_required
def update_server(id):
    response, status_code = ServerService.update_server(
        id,
        request.get_json(silent=True) or {}, current_user
    )

    return jsonify(response), status_code


@server.route("/add-server", methods=["POST"])
@admin_required
def add_server():
    response, status_code = ServerService.add_server(
        request.get_json(silent=True) or request.form.to_dict(), current_user
    )

    return jsonify(response), status_code


@server.route("/servers", methods=["GET"])
@login_required
def get_servers():
    response, status_code = ServerService.get_servers(current_user)
    return jsonify(response), status_code


@server.route("/servers/<id>", methods=["GET"])
@login_required
def get_server(id):
    response, status_code = ServerService.get_server(id, current_user)
    return jsonify(response), status_code


@server.route("/delete-server/<id>", methods=["POST", "DELETE"])
@admin_required
def delete_server(id):
    response, status_code = ServerService.delete_server(id, current_user)
    return jsonify(response), status_code


@server.route("/servers/<id>/rdp-test", methods=["GET", "POST"])
@login_required
def test_rdp_server(id):
    response, status_code = ServerService.test_rdp_server(id, current_user)
    return jsonify(response), status_code


@server.route("/connect-server/<id>", methods=["POST"])
@login_required
def connect_server(id):
    response, status_code = ServerService.connect_server(
        id,
        request.get_json(silent=True) or request.form.to_dict(), current_user
    )

    return jsonify(response), status_code
