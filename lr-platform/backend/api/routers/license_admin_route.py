from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from backend.api.routers.auth_route import admin_required
from backend.extensions import db
from backend.repositories.license_repository import LicenseActivationRepository
from backend.repositories.license_repository import ProductKeyRepository
from backend.repositories.license_repository import TrialSessionRepository
from backend.services.license_service import LicenseService
from backend.services.external_license_validator import LicenseServerUnavailable
from backend.services.user_license_service import UserLicenseService
from backend.models.user import User


license_admin = Blueprint("license_admin", __name__, url_prefix="/license")


def _service():
    return LicenseService(
        key_repository=ProductKeyRepository(db),
        activation_repository=LicenseActivationRepository(db),
        trial_repository=TrialSessionRepository(db),
    )


def _product_key_response(product_key):
    created_at = getattr(product_key, "created_at", None)
    return {
        "id": str(getattr(product_key, "id", "")),
        "key_code": getattr(product_key, "key_code", ""),
        "plan_name": getattr(product_key, "plan_name", "STANDARD"),
        "max_activations": getattr(product_key, "max_activations", 1),
        "valid_days": getattr(product_key, "valid_days", 365),
        "is_revoked": bool(getattr(product_key, "is_revoked", False)),
        "issued_to": getattr(product_key, "issued_to", None),
        "created_at": created_at.isoformat() if created_at else None,
    }


def _license_user_response(user):
    license_status = dict(UserLicenseService.get_status(user))
    license_status.pop("license_token", None)
    return {
        "id": User.get_id(user),
        "username": user.get("username"),
        "email": user.get("email"),
        "is_active": bool(user.get("is_active")),
        "license": license_status,
    }


def _license_user(user_id):
    user = User.get_by_id(user_id, tenant_id=current_user.get("tenant_id"))
    if not user:
        raise ValueError("User not found")
    if User.is_admin(user):
        raise ValueError("Admin accounts do not require a license")
    return user


@license_admin.route("/admin/keys", methods=["GET"])
@admin_required
def list_product_keys():
    return jsonify([
        _product_key_response(product_key)
        for product_key in _service().list_keys()
    ]), 200


@license_admin.route("/admin/keys/<key_code>/revoke", methods=["POST"])
@admin_required
def revoke_product_key(key_code):
    try:
        product_key = _service().revoke_key(key_code)
    except ValueError as error:
        return jsonify({"message": str(error)}), 404

    return jsonify(_product_key_response(product_key)), 200


@license_admin.route("/admin/users", methods=["GET"])
@admin_required
def list_user_licenses():
    tenant_id = current_user.get("tenant_id")
    users = [
        _license_user_response(user)
        for user in User.collection.find({"tenant_id": tenant_id}).sort("username", 1)
        if not User.is_admin(user)
    ]
    licensed = sum(
        1 for user in users
        if user.get("license", {}).get("status") == "LICENSED"
    )
    blocked = sum(
        1 for user in users
        if user.get("license", {}).get("blocked") is True
    )
    return jsonify({
        "users": users,
        "summary": {
            "total_users": len(users),
            "licensed": licensed,
            "blocked": blocked,
            "pending": max(0, len(users) - licensed),
        },
    }), 200


@license_admin.route("/admin/users/<user_id>/activate", methods=["POST"])
@admin_required
def activate_user_license(user_id):
    data = request.get_json(silent=True) or {}
    key_code = data.get("key_code") or data.get("key") or data.get("license_key")
    try:
        user = _license_user(user_id)
        activation = UserLicenseService.activate(user, str(key_code or "").strip())
    except LicenseServerUnavailable as error:
        return jsonify({"success": False, "message": str(error)}), 503
    except ValueError as error:
        status_code = 404 if str(error) == "User not found" else 400
        return jsonify({"success": False, "message": str(error)}), status_code

    return jsonify({
        "success": True,
        "message": f"License activated for {user.get('username')}",
        "activation": activation,
        "user": _license_user_response(user),
    }), 200


@license_admin.route("/me", methods=["GET"])
@login_required
def my_license_status():
    return jsonify(UserLicenseService.get_status(current_user)), 200


@license_admin.route("/me/activate", methods=["POST"])
@login_required
def activate_my_license():
    return jsonify({
        "success": False,
        "message": "License activation is managed by your administrator.",
    }), 403


@license_admin.route("/me/hold", methods=["POST"])
@login_required
def hold_my_license():
    data = request.get_json(silent=True) or {}
    UserLicenseService.hold(current_user, context=data.get("context"))
    return jsonify({
        "success": True,
        "license": UserLicenseService.get_status(current_user),
    }), 200
