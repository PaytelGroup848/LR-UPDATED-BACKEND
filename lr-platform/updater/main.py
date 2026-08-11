import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path
from tkinter import Tk, messagebox


def _show_error(app_name, message):
    root = Tk()
    root.withdraw()
    messagebox.showerror(f"{app_name} Update", message)
    root.destroy()


def _show_info(app_name, message):
    root = Tk()
    root.withdraw()
    messagebox.showinfo(f"{app_name} Update", message)
    root.destroy()


def _pid_exists(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _wait_for_exit(pid, timeout_seconds=60):
    started_at = time.time()
    while pid and _pid_exists(pid):
        if time.time() - started_at > timeout_seconds:
            return False
        time.sleep(0.5)
    return True


def _download(url, app_name):
    destination = Path(tempfile.gettempdir()) / f"lr-update-{app_name.replace(' ', '-').lower()}.exe"
    with urllib.request.urlopen(url, timeout=60) as response:
        with open(destination, "wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    return destination


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _retry_file_operation(operation, timeout_seconds=10):
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            return operation()
        except OSError as error:
            if error.winerror not in {5, 32} or time.monotonic() >= deadline:
                raise
            time.sleep(0.25)


def _remove_backup_best_effort(backup):
    try:
        _retry_file_operation(backup.unlink, timeout_seconds=2)
    except OSError:
        # The replacement is already complete. Antivirus scanners can briefly
        # retain a handle to the old executable, so cleanup must not turn a
        # successful update into a reported failure.
        pass


def _replace_file(source, target):
    source = Path(source)
    target = Path(target)
    backup = target.with_name(f"{target.name}.{uuid.uuid4().hex}.old")
    target_was_moved = False

    try:
        if target.exists():
            _retry_file_operation(lambda: target.replace(backup))
            target_was_moved = True
        _retry_file_operation(lambda: source.replace(target))
    except Exception:
        if target_was_moved and not target.exists() and backup.exists():
            _retry_file_operation(lambda: backup.replace(target))
        raise

    if target_was_moved and backup.exists():
        _remove_backup_best_effort(backup)


def main():
    parser = argparse.ArgumentParser(description="LR app updater")
    parser.add_argument("--app-name", default="LR App")
    parser.add_argument("--target", required=True)
    parser.add_argument("--download-url", required=True)
    parser.add_argument("--sha256", default="")
    parser.add_argument("--pid", type=int, default=0)
    parser.add_argument("--restart", action="store_true")
    args = parser.parse_args()

    target = Path(args.target)
    if not target.exists():
        _show_error(args.app_name, f"Target app not found:\n{target}")
        return 1

    try:
        if not _wait_for_exit(args.pid):
            _show_error(args.app_name, "App close nahi hua. App close karke update dobara try karein.")
            return 1

        downloaded = _download(args.download_url, args.app_name)

        expected_sha = args.sha256.strip().lower()
        if expected_sha and _sha256(downloaded).lower() != expected_sha:
            downloaded.unlink(missing_ok=True)
            _show_error(args.app_name, "Downloaded update file verify nahi ho paayi.")
            return 1

        _replace_file(downloaded, target)

        if args.restart:
            subprocess.Popen([str(target)], close_fds=True)

        _show_info(args.app_name, "Update completed.")
        return 0
    except Exception as error:
        _show_error(args.app_name, f"Update failed:\n{error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
