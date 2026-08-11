from functools import wraps

from flask import jsonify
from flask_login import current_user


def role_required(*roles):
    expected = {str(role).strip().replace(" ", "_").upper() for role in roles}

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user_role = str(getattr(current_user, "role", "") or "").upper()
            is_admin = bool(getattr(current_user, "is_admin", False))
            has_role = hasattr(current_user, "has_role") and current_user.has_role(*roles)
            if is_admin or user_role in expected or has_role:
                return fn(*args, **kwargs)
            return jsonify({"success": False, "error": "Forbidden"}), 403

        return wrapper

    return decorator


admin_required = role_required("ADMIN")
