import platform
import subprocess


def is_windows():
    return platform.system().lower() == "windows"


def open_path(path):
    if is_windows():
        subprocess.Popen(["explorer", str(path)])
        return {"success": True, "message": "Path opened"}
    return {"success": False, "error": "Windows shell is not available"}


def get_session_name():
    return platform.node()
