import os
from typing import Any, cast

from flask import Flask, jsonify, redirect, request, url_for
from flask_login import current_user

from backend.extensions import login_manager, socketio
from backend.microservices import get_service_spec
from backend.manager.logger import configure_logging

from backend.core.config_paths import INSTANCE_DIR, TEMPLATE_DIR, STATIC_DIR
from backend.api.router_registry import register_blueprints
from backend.sockets.socket_registry import register_socket_handlers, register_rdp_namespace
from backend.core.error_handlers import register_error_handlers
from backend.core.auth_loader import register_auth_loader
from backend.services.index_service import IndexService


def create_app(service_name=None):
    spec = get_service_spec(service_name or os.getenv("SERVICE_NAME", "gateway"))

    app = Flask(
        __name__,
        instance_path=INSTANCE_DIR,
        template_folder=TEMPLATE_DIR,
        static_folder=STATIC_DIR,
        static_url_path="/static",
    )

    app.config.from_object("backend.core.config")
    app.config.from_pyfile("config.py", silent=True)
    app.config["SERVICE_NAME"] = spec.name
    app.config["SERVICE_DESCRIPTION"] = spec.description

    os.makedirs(app.instance_path, exist_ok=True)
    configure_logging(app)

    login_manager_obj = cast(Any, login_manager)
    login_manager_obj.init_app(app)
    login_manager_obj.login_view = "auth.login" if "auth" in spec.blueprints else None

    socketio.init_app(app)

    register_blueprints(app, spec.blueprints)
    register_socket_handlers(spec)
    register_rdp_namespace(spec)
    register_error_handlers(app)
    register_auth_loader(spec)
    register_cors(app)

    register_basic_routes(app, spec)
    with app.app_context():
        IndexService.ensure_indexes()

    if app.config.get("PRINTING_ENABLED", True):
        from backend.printing import get_print_job_service

        get_print_job_service().start()

    return app


def register_cors(app):
    configured_app_origins = {
        str(app.config.get(config_key) or '').strip().rstrip('/')
        for config_key in ('FRONTEND_URL', 'LR_SERVER_URL', 'LR_BACKEND_URL')
        if str(app.config.get(config_key) or '').strip()
    }
    configured_origins = app.config.get("CORS_ORIGINS") or os.getenv("CORS_ORIGINS")
    allowed_origins = {
        origin.strip()
        for origin in str(configured_origins or "").split(",")
        if origin.strip()
    }
    allowed_origins.update(configured_app_origins)
    allow_any_origin = "*" in allowed_origins and app.config.get("ENVIRONMENT") != "production"
    if "*" in allowed_origins and app.config.get("ENVIRONMENT") == "production":
        app.logger.warning("Ignoring wildcard CORS origin in production")
        allowed_origins.discard("*")

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin")
        if origin and (origin in allowed_origins or allow_any_origin):
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = (
                "Content-Type, Authorization, X-Requested-With"
            )
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            )
        return response


def register_basic_routes(app, spec):
    @app.route("/")
    def home():
        if spec.name in ("gateway", "portal"):
            if current_user.is_authenticated:
                return redirect(url_for("portal.portal_home"))

            return redirect(
                url_for("auth.login") if "auth" in spec.blueprints else "/health"
            )

        return jsonify({
            "service": spec.name,
            "description": spec.description,
            "status": "ok",
        })

    @app.route("/health")
    def health():
        return jsonify({
            "service": spec.name,
            "status": "ok",
            "blueprints": list(spec.blueprints),
        })

    @app.route("/test")
    def test():
        return f"{spec.name} service working"

    @app.route("/test_socket")
    def test_socket():
        socketio.emit("message", {
            "data": f"Hello from the {spec.name} service!"
        })
        return "Socket test emitted"
