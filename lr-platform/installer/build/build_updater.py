"""
Builds the LR Updater helper exe.

Output:
    backend/static/updater/LR Updater.exe
"""

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
UPDATER_DIR = ROOT_DIR / "updater"
DOWNLOAD_DIR = ROOT_DIR / "backend" / "static" / "updater"
MANIFEST_DIR = ROOT_DIR / "backend" / "static" / "app-updates"
BUILD_DIR = ROOT_DIR / "installer" / "build"
WORK_DIR = BUILD_DIR / "work"
SPEC_DIR = BUILD_DIR / "specs"

APP_NAME = "LR Updater"
ENTRY_SCRIPT = UPDATER_DIR / "main.py"


def _build_version():
    return datetime.now(timezone.utc).strftime("%Y.%m.%d.%H%M%S")


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(version, exe_path):
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "app_id": "lr-updater",
        "app_name": APP_NAME,
        "version": version,
        "file_name": exe_path.name,
        "file_path": str(exe_path),
        "sha256": _sha256(exe_path),
        "released_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    (MANIFEST_DIR / "lr-updater.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def main():
    version = _build_version()

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    SPEC_DIR.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable, "-m", "PyInstaller",
        str(ENTRY_SCRIPT),
        "--name", APP_NAME,
        "--onefile",
        "--windowed",
        "--clean",
        "--noconfirm",
        "--distpath", str(DOWNLOAD_DIR),
        "--workpath", str(WORK_DIR),
        "--specpath", str(SPEC_DIR),
    ]

    print("Running:", " ".join(command))
    subprocess.run(command, check=True)

    exe_path = DOWNLOAD_DIR / f"{APP_NAME}.exe"
    if not exe_path.exists():
        raise FileNotFoundError(f"Build failed: {exe_path} was not created.")

    _write_manifest(version, exe_path)
    print(f"\nDone. LR Updater exe ready at: {exe_path}")


if __name__ == "__main__":
    main()
