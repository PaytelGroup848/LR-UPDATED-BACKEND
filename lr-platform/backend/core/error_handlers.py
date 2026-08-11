from flask import jsonify
from werkzeug.exceptions import HTTPException

from backend.tenancy.context import TenantScopeError


def register_error_handlers(app):
    @app.errorhandler(TenantScopeError)
    def handle_tenant_scope_error(error):
        message = str(error)
        tenant_required = (
            "not assigned to a tenant" in message
            or "Tenant context is required" in message
        )
        return jsonify({
            "success": False,
            "message": message,
            "code": "tenant_required" if tenant_required else "tenant_scope_violation",
        }), 423 if tenant_required else 403

    @app.errorhandler(Exception)
    def log_unhandled_exception(error):
        if isinstance(error, HTTPException):
            return error

        app.logger.exception("Unhandled exception")
        raise error
