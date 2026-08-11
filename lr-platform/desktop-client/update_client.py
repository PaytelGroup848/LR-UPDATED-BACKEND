import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from tkinter import messagebox


UPDATER_FILE_NAME = "LR Updater.exe"


def is_packaged_exe():
    return bool(getattr(sys, "frozen", False))


def check_for_update(base_url, app_id, current_version):
    if not is_packaged_exe():
        return None

    query = urllib.parse.urlencode({"current_version": current_version})
    url = f"{base_url.rstrip('/')}/api/app-updates/{app_id}?{query}"
    with urllib.request.urlopen(url, timeout=8) as response:
        data = json.loads(response.read().decode("utf-8"))

    if not data.get("success") or not data.get("update_available"):
        return None
    return data


def _resource_updater_path():
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base_path / "resources" / UPDATER_FILE_NAME


def _local_updater_path():
    root = Path(os.getenv("LOCALAPPDATA") or tempfile.gettempdir())
    return root / "LR Remote Access" / UPDATER_FILE_NAME


def _download_file(url, destination):
    with urllib.request.urlopen(url, timeout=60) as response:
        with open(destination, "wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)


def ensure_updater(info):
    destination = _local_updater_path()
    destination.parent.mkdir(parents=True, exist_ok=True)

    embedded = _resource_updater_path()
    if embedded.exists():
        shutil.copy2(embedded, destination)
        return destination

    updater_url = info.get("updater_download_url")
    if not updater_url:
        raise RuntimeError("Updater download URL missing")

    _download_file(updater_url, destination)
    return destination


def prompt_and_launch_update(parent, info, app_name):
    latest = info.get("latest_version") or "latest"
    current = info.get("current_version") or "current"
    answer = messagebox.askyesno(
        f"{app_name} Update",
        (
            f"New update available.\n\n"
            f"Current: {current}\n"
            f"Latest: {latest}\n\n"
            "Download and install now?"
        ),
        parent=parent,
    )
    if not answer:
        return False

    if not is_packaged_exe():
        messagebox.showinfo(
            f"{app_name} Update",
            "Update sirf packaged .exe me chalega.",
            parent=parent,
        )
        return False

    updater = ensure_updater(info)
    subprocess.Popen(
        [
            str(updater),
            "--app-name", app_name,
            "--target", sys.executable,
            "--download-url", info["download_url"],
            "--sha256", info.get("sha256") or "",
            "--pid", str(os.getpid()),
            "--restart",
        ],
        close_fds=True,
    )
    parent.after(500, parent.destroy)
    return True
