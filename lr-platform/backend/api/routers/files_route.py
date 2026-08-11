from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from backend.services.files_service import FileService
from backend.services.user_license_service import UserLicenseService
from backend.tenancy.privileged import require_configured_agent


files = Blueprint("files", __name__)
files.before_request(require_configured_agent)


def _error(message, code=400):
    return jsonify({"success": False, "message": message}), code


def _success(data):
    return jsonify({"success": True, "data": data})


def _license_gate(action):
    blocked = UserLicenseService.block_response(current_user, context={"action": action})
    if blocked:
        result, status_code = blocked
        return jsonify(result), status_code
    return None


@files.route("/files", methods=["GET"])
@login_required
def get_files():
    blocked = _license_gate("list_files")
    if blocked:
        return blocked

    path = request.args.get("path", ".")

    try:
        result = FileService.list_files(path)
        return _success(result)
    except ValueError:
        return _error("Invalid path", 403)
    except OSError as error:
        return _error(str(error), 500)


@files.route("/read-file")
@login_required
def get_file():
    blocked = _license_gate("read_file")
    if blocked:
        return blocked

    response, status_code = FileService.read_file_content(
        request.args.get("path")
    )

    return jsonify(response), status_code


@files.route("/create-file", methods=["POST"])
@login_required
def new_file():
    blocked = _license_gate("create_file")
    if blocked:
        return blocked

    response, status_code = FileService.create_file_content(
        request.form.get("path"),
        request.form.get("content", "")
    )

    return jsonify(response), status_code


@files.route("/upload-file", methods=["POST"])
@login_required
def upload_file():
    blocked = _license_gate("upload_file")
    if blocked:
        return blocked

    response, status_code = FileService.upload_file_content(
        request.files.get("file"),
        request.form.get("path")
    )

    return jsonify(response), status_code


@files.route("/delete-file", methods=["POST"])
@login_required
def delete_file_route():
    blocked = _license_gate("delete_file")
    if blocked:
        return blocked

    response, status_code = FileService.delete_file_content(
        request.form.get("path"),
        current_user.id
    )

    return jsonify(response), status_code


@files.route("/paste-file", methods=["POST"])
@login_required
def paste_file_route():
    blocked = _license_gate("paste_file")
    if blocked:
        return blocked

    response, status_code = FileService.paste_file_content(
        request.form.get("source"),
        request.form.get("destination"),
        request.form.get("mode", "copy"),
        str(request.form.get("overwrite", "")).lower() in {"1", "true", "yes", "on"},
    )

    return jsonify(response), status_code
