from flask import current_app, jsonify, request


def require_configured_agent():
    """Fail closed until the route is dispatched to an enrolled tenant agent."""
    if current_app.config.get("ALLOW_LEGACY_LOCAL_HOST_OPERATIONS", False):
        return None
    return jsonify({
        "success": False,
        "message": "Local backend host operations are disabled; use an enrolled server agent",
        "code": "tenant_agent_required",
        "server_id": request.values.get("server_id"),
    }), 503
