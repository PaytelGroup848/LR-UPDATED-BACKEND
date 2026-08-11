import platform

from shared.windows.remote_app import run_remote_app_action


def sync_remote_app(payload):
    if platform.system().lower() != "windows":
        return {
            "success": False,
            "status": "failed",
            "message": "The LR Agent must run on the Windows RDS server.",
        }
    return run_remote_app_action(payload or {})
