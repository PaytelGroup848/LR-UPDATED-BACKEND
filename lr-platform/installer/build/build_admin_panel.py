"""
Builds the LR Admin Panel into a single Windows exe with the LR logo.

Usage (from repo root, inside a venv with admin-panel/requirements.txt
installed):

    python installer/build/build_admin_panel.py

Output:
    backend/static/admin/Admin Panel.exe
"""

import os
import sys
import hashlib
import json
import shutil
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
ADMIN_PANEL_DIR = ROOT_DIR / "admin-panel"
ADMIN_RESOURCES_DIR = ADMIN_PANEL_DIR / "resources"
BUILD_DIR = ROOT_DIR / "installer" / "build"
INSTALLER_RESOURCES_DIR = ROOT_DIR / "installer" / "resources"
DOWNLOAD_DIR = ROOT_DIR / "backend" / "static" / "admin"
UPDATER_EXE = ROOT_DIR / "backend" / "static" / "updater" / "LR Updater.exe"
AGENT_EXE = BUILD_DIR / "output" / "LR_Agent.exe"
MANIFEST_DIR = ROOT_DIR / "backend" / "static" / "app-updates"
VERSION_FILE = ADMIN_PANEL_DIR / "build_version.py"

LEGACY_OUTPUT_DIR = BUILD_DIR / "output"

APP_NAME = "Admin Panel"
LEGACY_APP_NAME = "LR_Admin_Panel"
ENTRY_SCRIPT = ADMIN_PANEL_DIR / "main.py"
LOGO_PATH = ADMIN_RESOURCES_DIR / "lr-remote-logo.png"
ICON_PATH = INSTALLER_RESOURCES_DIR / "lr_admin_panel.ico"
FALLBACK_ICON_PATH = ROOT_DIR / "desktop-client" / "resources" / "lr-remote-logo.ico"
SOURCE_SUFFIXES = {".py", ".png", ".ico"}
BUILD_LOCK_TIMEOUT_SECONDS = 10 * 60
BUILD_LOCK_PATH = Path(tempfile.gettempdir()) / (
    "lr-admin-panel-build-"
    f"{hashlib.sha256(str(ROOT_DIR).encode('utf-8')).hexdigest()[:16]}.lock"
)


def _build_version():
    return datetime.now(timezone.utc).strftime("%Y.%m.%d.%H%M%S")


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_version_file(version, path=VERSION_FILE):
    path.write_text(
        f'APP_VERSION = "{version}"\n',
        encoding="utf-8",
    )


def _source_hash(root):
    digest = hashlib.sha256()
    files = sorted(
        path for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SOURCE_SUFFIXES
        and path.name != VERSION_FILE.name
        and "__pycache__" not in path.parts
    )
    for path in files:
        relative_path = path.relative_to(root).as_posix()
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _atomic_write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary_path.write_text(text, encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _lock_file(handle):
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(handle):
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _exclusive_build_lock(timeout_seconds=BUILD_LOCK_TIMEOUT_SECONDS):
    BUILD_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = open(BUILD_LOCK_PATH, "a+b")
    locked = False
    deadline = time.monotonic() + timeout_seconds
    announced_wait = False
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()

        while True:
            try:
                _lock_file(handle)
                locked = True
                break
            except OSError as error:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        "Timed out waiting for another Admin Panel build to finish."
                    ) from error
                if not announced_wait:
                    print("Another Admin Panel build is running; waiting for it to finish...")
                    announced_wait = True
                time.sleep(0.5)

        yield
    finally:
        if locked:
            _unlock_file(handle)
        handle.close()


def _write_manifest(version, exe_path):
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "app_id": "admin-panel",
        "app_name": APP_NAME,
        "version": version,
        "file_name": exe_path.name,
        "file_path": str(exe_path),
        "sha256": _sha256(exe_path),
        "released_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    _atomic_write_text(
        MANIFEST_DIR / "admin-panel.json",
        json.dumps(payload, indent=2, sort_keys=True),
    )


def _ensure_updater():
    if UPDATER_EXE.exists():
        return

    subprocess.run(
        [sys.executable, str(BUILD_DIR / "build_updater.py")],
        check=True,
    )


def _build_agent():
    source_files = [
        path
        for root in (ROOT_DIR / "agent", ROOT_DIR / "shared")
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".py", ".txt"}
    ]
    source_files.extend([
        BUILD_DIR / "build_agent.py",
        ROOT_DIR / "agent" / "requirements.txt",
    ])
    newest_source = max(
        (path.stat().st_mtime for path in source_files if path.exists()),
        default=0,
    )
    if AGENT_EXE.exists() and AGENT_EXE.stat().st_mtime >= newest_source:
        return
    subprocess.run(
        [sys.executable, str(BUILD_DIR / "build_agent.py")],
        cwd=ROOT_DIR,
        check=True,
    )
    if not AGENT_EXE.exists():
        raise FileNotFoundError(f"Combined package Agent was not built: {AGENT_EXE}")


def _ensure_icon():
    if ICON_PATH.exists() or not LOGO_PATH.exists():
        return

    try:
        from PIL import Image
    except ImportError:
        print("Pillow is not installed; building without an icon.")
        return

    ICON_PATH.parent.mkdir(parents=True, exist_ok=True)
    image = Image.open(LOGO_PATH).convert("RGBA")
    image.save(
        ICON_PATH,
        sizes=[
            (16, 16),
            (24, 24),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )
    print(f"Created icon: {ICON_PATH}")


def _remove_old_outputs():
    stale_paths = [
        LEGACY_OUTPUT_DIR / LEGACY_APP_NAME,
        DOWNLOAD_DIR / f"{LEGACY_APP_NAME}.exe",
    ]

    for path in stale_paths:
        if path.is_dir():
            shutil.rmtree(path)
            print(f"Removed old folder: {path}")
        elif path.exists():
            path.unlink()
            print(f"Removed old file: {path}")


def _copy_source_snapshot(destination):
    shutil.copytree(
        ADMIN_PANEL_DIR,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def _run_source_smoke_test(source_dir):
    subprocess.run(
        [sys.executable, str(source_dir / "main.py"), "--smoke-test"],
        cwd=source_dir,
        check=True,
        timeout=30,
    )


def _run_packaged_smoke_test(exe_path):
    subprocess.run(
        [str(exe_path), "--smoke-test"],
        check=True,
        timeout=60,
    )


def _publish_executable(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        shutil.copy2(source, temporary_path)
        os.replace(temporary_path, target)
    finally:
        temporary_path.unlink(missing_ok=True)


def _build_and_publish():
    version = _build_version()

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    _ensure_updater()
    _build_agent()
    _ensure_icon()
    _remove_old_outputs()
    initial_source_hash = _source_hash(ADMIN_PANEL_DIR)

    with tempfile.TemporaryDirectory(
        prefix="admin-panel-build-",
        dir=BUILD_DIR,
        ignore_cleanup_errors=True,
    ) as temporary_directory:
        staging_root = Path(temporary_directory)
        source_dir = staging_root / "source"
        dist_dir = staging_root / "dist"
        work_dir = staging_root / "work"
        spec_dir = staging_root / "specs"

        _copy_source_snapshot(source_dir)
        snapshot_source_hash = _source_hash(source_dir)
        if snapshot_source_hash != initial_source_hash:
            raise RuntimeError(
                "Admin Panel source changed while its snapshot was being created. "
                "The build was cancelled; retry after edits settle."
            )
        _write_version_file(version, source_dir / VERSION_FILE.name)
        _run_source_smoke_test(source_dir)

        staged_entry_script = source_dir / ENTRY_SCRIPT.name
        staged_resources_dir = source_dir / "resources"
        command = [
            sys.executable, "-m", "PyInstaller",
            str(staged_entry_script),
            "--name", APP_NAME,
            "--onefile",
            "--windowed",
            "--clean",
            "--noconfirm",
            "--distpath", str(dist_dir),
            "--workpath", str(work_dir),
            "--specpath", str(spec_dir),
            "--paths", str(source_dir),
            "--add-data", f"{staged_resources_dir}{os.pathsep}resources",
            "--add-data", f"{UPDATER_EXE}{os.pathsep}resources",
            "--add-data", f"{AGENT_EXE}{os.pathsep}resources/agent",
        ]

        icon_path = ICON_PATH if ICON_PATH.exists() else FALLBACK_ICON_PATH
        if icon_path.exists():
            command += ["--icon", str(icon_path)]

        print("Running:", " ".join(command))
        subprocess.run(command, check=True)

        staged_exe_path = dist_dir / f"{APP_NAME}.exe"
        if not staged_exe_path.exists():
            raise FileNotFoundError(f"Build failed: {staged_exe_path} was not created.")

        _run_packaged_smoke_test(staged_exe_path)
        if _source_hash(ADMIN_PANEL_DIR) != snapshot_source_hash:
            raise RuntimeError(
                "Admin Panel source changed during the build. "
                "The staged package was discarded; retry after edits settle."
            )

        exe_path = DOWNLOAD_DIR / f"{APP_NAME}.exe"
        _publish_executable(staged_exe_path, exe_path)

    _write_version_file(version)
    _write_manifest(version, exe_path)
    print(f"\nDone. Validated Admin Panel exe ready at: {exe_path}")


def main():
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    with _exclusive_build_lock():
        _build_and_publish()


if __name__ == "__main__":
    main()
