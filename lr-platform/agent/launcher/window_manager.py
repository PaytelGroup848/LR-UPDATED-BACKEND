def focus_window(title=None, pid=None):
    return {
        "success": False,
        "error": "Native window focusing is not configured",
        "title": title,
        "pid": pid,
    }


def list_windows():
    return []
