from flask import Blueprint, jsonify, request, send_file
from flask_login import login_required

from backend.services.windows_service import WindowsFileService
from backend.tenancy.privileged import require_configured_agent


windows = Blueprint("windows", __name__)
windows.before_request(require_configured_agent)


@windows.route("/drives", methods=["GET"])
@login_required
def drives():
    response, status_code = WindowsFileService.get_drives()
    return jsonify(response), status_code


@windows.route("/browse", methods=["GET"])
@login_required
def browse():
    response, status_code = WindowsFileService.browse(
        request.args.get("path")
    )
    return jsonify(response), status_code


@windows.route("/create-folder", methods=["POST"])
@login_required
def create_new_folder():
    response, status_code = WindowsFileService.create_folder(
        request.form.get("path")
    )
    return jsonify(response), status_code


@windows.route("/delete-path", methods=["POST"])
@login_required
def delete():
    response, status_code = WindowsFileService.delete_path(
        request.form.get("path")
    )
    return jsonify(response), status_code


@windows.route("/rename-file", methods=["POST"])
@login_required
def rename():
    response, status_code = WindowsFileService.rename_file(
        request.form.get("old_path"),
        request.form.get("new_path")
    )
    return jsonify(response), status_code


@windows.route("/move-file", methods=["POST"])
@login_required
def move():
    response, status_code = WindowsFileService.move_file(
        request.form.get("source"),
        request.form.get("destination")
    )
    return jsonify(response), status_code


@windows.route("/copy-file", methods=["POST"])
@login_required
def copy():
    response, status_code = WindowsFileService.copy_file(
        request.form.get("source"),
        request.form.get("destination")
    )
    return jsonify(response), status_code


@windows.route("/paste-path", methods=["POST"])
@login_required
def paste():
    response, status_code = WindowsFileService.paste_path(
        request.form.get("source"),
        request.form.get("destination"),
        request.form.get("mode", "copy"),
        str(request.form.get("overwrite", "")).lower() in {"1", "true", "yes", "on"},
    )
    return jsonify(response), status_code


@windows.route("/windows/upload-file", methods=["POST"])
@login_required
def upload_file():
    response, status_code = WindowsFileService.upload_file(
        request.files.get("file"),
        request.form.get("path")
    )
    return jsonify(response), status_code


@windows.route("/download-file", methods=["GET"])
@login_required
def download_file():
    response, status_code = WindowsFileService.get_download_path(
        request.args.get("path")
    )

    if status_code != 200:
        return jsonify(response), status_code

    return send_file(
        response["path"],
        as_attachment=True,
        download_name=response.get("download_name"),
    )
