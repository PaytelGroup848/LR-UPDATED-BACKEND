from flask import Blueprint, jsonify, request, send_file
from flask_login import current_user, login_required

from backend.services.portal_customization_service import (
    PortalCustomizationError,
    PortalCustomizationService,
)


portal_customization_bp = Blueprint("portal_customization", __name__)


def _is_admin():
    return bool(
        getattr(current_user, "is_admin", False)
        or (
            hasattr(current_user, "has_role")
            and current_user.has_role("Admin")
        )
    )


def _admin_forbidden():
    return jsonify({
        "success": False,
        "error": "Administrator permission is required",
        "code": "admin_required",
    }), 403


def _service_error(error):
    return jsonify({
        "success": False,
        "error": str(error),
        "code": error.code,
    }), error.status_code


@portal_customization_bp.route(
    "/api/admin/portal-customization/draft",
    methods=["GET", "PUT", "PATCH"],
)
@login_required
def portal_customization_draft():
    if not _is_admin():
        return _admin_forbidden()
    try:
        if request.method == "GET":
            return jsonify(PortalCustomizationService.get_draft(current_user))
        payload = request.get_json(silent=True) or {}
        config = payload.get("config", payload)
        return jsonify(
            PortalCustomizationService.save_draft(
                current_user,
                config,
                ip_address=request.remote_addr,
            )
        )
    except PortalCustomizationError as error:
        return _service_error(error)


@portal_customization_bp.get("/api/admin/portal-customization/preview")
@login_required
def portal_customization_preview():
    if not _is_admin():
        return _admin_forbidden()
    try:
        return jsonify(PortalCustomizationService.get_draft(current_user))
    except PortalCustomizationError as error:
        return _service_error(error)


@portal_customization_bp.post("/api/admin/portal-customization/publish")
@login_required
def publish_portal_customization():
    if not _is_admin():
        return _admin_forbidden()
    try:
        return jsonify(
            PortalCustomizationService.publish(
                current_user,
                ip_address=request.remote_addr,
            )
        )
    except PortalCustomizationError as error:
        return _service_error(error)


@portal_customization_bp.post("/api/admin/portal-customization/reset")
@login_required
def reset_portal_customization():
    if not _is_admin():
        return _admin_forbidden()
    try:
        return jsonify(
            PortalCustomizationService.reset_draft(
                current_user,
                ip_address=request.remote_addr,
            )
        )
    except PortalCustomizationError as error:
        return _service_error(error)


@portal_customization_bp.post(
    "/api/admin/portal-customization/upload/<asset_type>"
)
@login_required
def upload_portal_customization_asset(asset_type):
    if not _is_admin():
        return _admin_forbidden()
    try:
        return jsonify(
            PortalCustomizationService.upload_asset(
                current_user,
                asset_type,
                request.files.get("file"),
                ip_address=request.remote_addr,
            )
        )
    except PortalCustomizationError as error:
        return _service_error(error)


@portal_customization_bp.get(
    "/api/admin/portal-customization/assets/<filename>"
)
@login_required
def admin_portal_customization_asset(filename):
    if not _is_admin():
        return _admin_forbidden()
    try:
        path = PortalCustomizationService.admin_asset_path(
            current_user,
            filename,
        )
        response = send_file(path, conditional=True, max_age=0)
        response.headers["Cache-Control"] = "private, no-store"
        return response
    except PortalCustomizationError as error:
        return _service_error(error)


@portal_customization_bp.get("/api/public/portal-customization")
def public_portal_customization():
    return jsonify(
        PortalCustomizationService.public_settings(
            request.args.get("company_code")
            or request.args.get("company")
        )
    )


@portal_customization_bp.get(
    "/api/public/portal-customization/assets/<company_code>/<filename>"
)
def public_portal_customization_asset(company_code, filename):
    try:
        path = PortalCustomizationService.public_asset_path(
            company_code,
            filename,
        )
        response = send_file(path, conditional=True, max_age=3600)
        response.headers["Cache-Control"] = "public, max-age=3600, immutable"
        return response
    except (PortalCustomizationError, ValueError):
        return jsonify({
            "success": False,
            "error": "Portal asset not found",
            "code": "portal_asset_not_found",
        }), 404
