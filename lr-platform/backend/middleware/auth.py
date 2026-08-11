from functools import wraps

from flask import jsonify
from flask_login import current_user


def login_required_json(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"success": False, "error": "Authentication required"}), 401
        return fn(*args, **kwargs)

    return wrapper
