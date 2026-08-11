from flask import jsonify, redirect, request, url_for
from backend.extensions import login_manager
from backend.models.user import User


def register_auth_loader(spec):
    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/lr/"):
            return jsonify({
                "success": False,
                "error": "Authentication required",
            }), 401

        wants_json = (
            request.path.startswith(("/api/", "/portal/api/", "/users", "/servers"))
            or request.is_json
            or request.accept_mimetypes.best == "application/json"
        )
        if wants_json:
            return jsonify({
                "message": "Authentication required",
                "service": spec.name,
            }), 401

        if "auth" in spec.blueprints:
            return redirect(url_for("auth.login"))

        return jsonify({
            "message": "Authentication required",
            "service": spec.name,
        }), 401

    @login_manager.user_loader
    def load_user(user_id):
        return User.get_by_id(user_id)
