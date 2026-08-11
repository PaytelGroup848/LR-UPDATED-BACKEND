import re

from bson import ObjectId
from flask import Blueprint, jsonify, request
from flask_login import current_user

from backend.api.routers.auth_route import admin_required
from backend.services.apps_service import AppService
from backend.services.apps_service import ApplicationService

apps_bp = Blueprint("apps", __name__, url_prefix="/api/apps")


def _slugify(value):
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return slug or "app"


def _payload():
    data = request.get_json(silent=True)
    if data is not None:
        return data
    return request.form.to_dict(flat=False) if request.form else {}


def _payload_list(data, key):
    value = data.get(key, [])
    if isinstance(value, list):
        return value
    return [value]


def _as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _object_id(value):
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return None


def _doc_id(doc):
    return doc.get("_id") if doc else None


def _current_user_id():
    if hasattr(current_user, "get"):
        return current_user.get("_id")
    return getattr(current_user, "id", None)


def _current_user_id_str():
    user_id = _current_user_id()
    return str(user_id) if user_id else None


@apps_bp.route("", methods=["GET"])
@admin_required
def list_apps():
    result = ApplicationService.list_apps(_current_user_id())
    return jsonify(result), 200

@apps_bp.route("", methods=["POST"])
@admin_required
def create_app():
    result, status = ApplicationService.create_app(
        data=_payload(),
        user_id=_current_user_id(),
        ip_address=request.remote_addr
    )

    return jsonify(result), status

@apps_bp.route("/<app_id>", methods=["PATCH", "POST"])
@admin_required
def update_app(app_id):

    result, status = ApplicationService.update_app(
        app_id=app_id,
        data=_payload(),
        user_id=_current_user_id(),
        ip_address=request.remote_addr
    )

    return jsonify(result), status


@apps_bp.route("/<app_id>", methods=["DELETE"])
@admin_required
def delete_app(app_id):

    result, status = ApplicationService.delete_app(
        app_id=app_id,
        user_id=_current_user_id(),
        ip_address=request.remote_addr
    )

    return jsonify(result), status


@apps_bp.route("/<app_id>/remoteapp/sync", methods=["POST"])
@admin_required
def retry_remote_app(app_id):
    result, status = ApplicationService.retry_remote_app(
        app_id=app_id,
        user_id=_current_user_id(),
        ip_address=request.remote_addr,
    )
    return jsonify(result), status

@apps_bp.route("/<app_id>/assign", methods=["POST"])
@admin_required
def assign_app(app_id):

    result, status = ApplicationService.assign_app(
        app_id=app_id,
        data=_payload(),
        user_id=_current_user_id(),
        ip_address=request.remote_addr
    )

    return jsonify(result), status

@apps_bp.route("/assignments/user/<user_id>", methods=["GET"])
@admin_required
def user_assignments(user_id):

    result, status = ApplicationService.user_assignments(
        user_id=user_id,
        admin_user_id=_current_user_id(),
    )

    return jsonify(result), status


@apps_bp.route("/assignments/bulk", methods=["POST"])
@admin_required
def bulk_assign_apps():

    data = _payload()

    result = ApplicationService.bulk_assign_apps(
        user_ids=_payload_list(data, "user_ids"),
        app_ids=_payload_list(data, "app_ids"),
        enabled=_as_bool(data.get("is_enabled"), True),
        admin_user_id=_current_user_id(),
        ip_address=request.remote_addr
    )

    return jsonify(result), 200


@apps_bp.route("/upload", methods=["POST"])
@admin_required
def upload_software():

    result, status_code = AppService.upload_software(
        uploaded_file=request.files.get("file"),
        admin_user_id=_current_user_id(),
        ip_address=request.remote_addr
    )

    return jsonify(result), status_code


@apps_bp.route("/<app_id>/assign/<user_id>", methods=["DELETE"])
@admin_required
def unassign_app(app_id, user_id):

    result, status_code = AppService.unassign_app(
        app_id=app_id,
        user_id=user_id,
        admin_user_id=_current_user_id(),
        ip_address=request.remote_addr,
    )

    return jsonify(result), status_code
