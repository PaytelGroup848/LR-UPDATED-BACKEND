def register_blueprints(app, blueprint_names):
    from backend.api.routers.admin_features_route import admin_features
    from backend.api.routers.agent_route import agent_bp
    from backend.api.routers.apps_route import apps_bp
    from backend.api.routers.auth_route import auth
    from backend.api.routers.files_route import files
    from backend.api.routers.logs_route import logs
    from backend.api.routers.lr_route import lr_bp
    from backend.api.routers.license_admin_route import license_admin
    from backend.api.routers.portal_route import portal_bp
    from backend.api.routers.process_route import process
    from backend.api.routers.printing_route import printing_bp
    from backend.api.routers.server_route import server
    from backend.api.routers.sessions_route import sessions_bp
    from backend.api.routers.terminal_route import terminal
    from backend.api.routers.tenants_route import tenants_bp
    from backend.api.routers.windows_route import windows
    from backend.api.routers.windows_services_route import services

    registry = {
        "admin_features": admin_features,
        "agent": agent_bp,
        "apps": apps_bp,
        "auth": auth,
        "files": files,
        "logs": logs,
        "lr": lr_bp,
        "license_admin": license_admin,
        "portal": portal_bp,
        "process": process,
        "printing": printing_bp,
        "server": server,
        "services": services,
        "sessions": sessions_bp,
        "terminal": terminal,
        "tenants": tenants_bp,
        "windows": windows,
    }

    for name in blueprint_names:
        if name in registry:
            app.register_blueprint(registry[name])

    if "auth" in blueprint_names and "tenants" not in blueprint_names:
        app.register_blueprint(tenants_bp)
