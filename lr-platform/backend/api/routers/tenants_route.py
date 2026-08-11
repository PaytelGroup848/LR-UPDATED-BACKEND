from flask import Blueprint, jsonify, request

from backend.services.tenant_registration_service import (
    TenantRegistrationError,
    TenantRegistrationService,
)


tenants_bp = Blueprint("tenants", __name__, url_prefix="/api/companies")


@tenants_bp.post("/register")
def register_company():
    try:
        result = TenantRegistrationService.register(
            request.get_json(silent=True) or request.form,
            remote_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )
        return jsonify(result), 201
    except TenantRegistrationError as error:
        return jsonify({"success": False, "message": str(error), "code": error.code}), error.status_code
    except Exception:
        return jsonify({"success": False, "message": "Company registration failed"}), 500
