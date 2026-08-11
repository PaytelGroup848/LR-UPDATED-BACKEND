import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


TASK_NAME = "LR Remote Access Agent"


def _resource_path(*parts):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base.joinpath("resources", *parts)


def _is_admin():
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def _paths():
    program_files = Path(os.getenv("ProgramFiles") or r"C:\Program Files")
    program_data = Path(os.getenv("PROGRAMDATA") or r"C:\ProgramData")
    install_dir = program_files / "LR Remote Access Agent"
    state_dir = program_data / "LR Remote Access" / "Agent"
    return install_dir, state_dir


def _run(command, *, check=True):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=60,
        check=check,
    )


def install_and_start(server_url, enrollment_token):
    if os.name != "nt":
        return False, "The LR Windows Agent can only be installed on Windows."
    if not _is_admin():
        return False, "Close Admin Panel and run it as Administrator, then try again."
    bundled_agent = _resource_path("agent", "LR_Agent.exe")
    if not bundled_agent.exists():
        return False, "This Admin Panel package does not contain LR_Agent.exe. Install the latest combined build."

    install_dir, state_dir = _paths()
    install_dir.mkdir(parents=True, exist_ok=True)
    state_dir.mkdir(parents=True, exist_ok=True)
    target = install_dir / "LR_Agent.exe"

    _run(["schtasks", "/End", "/TN", TASK_NAME], check=False)
    shutil.copy2(bundled_agent, target)

    # Lock the directory before creating bootstrap.json so new state files
    # inherit usable SYSTEM/Administrators permissions. Applying only
    # (OI)(CI) grants recursively after a file already exists can leave that
    # file with an empty ACL on Windows.
    _run([
        "icacls",
        str(state_dir),
        "/inheritance:r",
        "/grant:r",
        "*S-1-5-18:(OI)(CI)F",
        "*S-1-5-32-544:(OI)(CI)F",
    ])
    _run([
        "icacls",
        str(state_dir / "*"),
        "/inheritance:r",
        "/grant:r",
        "*S-1-5-18:F",
        "*S-1-5-32-544:F",
        "/T",
        "/C",
    ], check=False)

    bootstrap = {
        "server_url": str(server_url or "").rstrip("/"),
        "enrollment_token": str(enrollment_token or "").strip(),
    }
    bootstrap_path = state_dir / "bootstrap.json"
    temporary = bootstrap_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(bootstrap, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(bootstrap_path)

    _run([
        "icacls",
        str(bootstrap_path),
        "/inheritance:r",
        "/grant:r",
        "*S-1-5-18:F",
        "*S-1-5-32-544:F",
    ])
    _run([
        "schtasks",
        "/Create",
        "/TN",
        TASK_NAME,
        "/SC",
        "ONSTART",
        "/RU",
        "SYSTEM",
        "/RL",
        "HIGHEST",
        "/TR",
        f'"{target}"',
        "/F",
    ])
    _run([
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        (
            "$settings = New-ScheduledTaskSettingsSet "
            "-ExecutionTimeLimit ([TimeSpan]::Zero) "
            "-RestartCount 999 "
            "-RestartInterval (New-TimeSpan -Minutes 1) "
            "-StartWhenAvailable; "
            "Set-ScheduledTask -TaskName 'LR Remote Access Agent' "
            "-Settings $settings | Out-Null"
        ),
    ])
    _run(["schtasks", "/Run", "/TN", TASK_NAME])
    return True, "LR Agent installed, enrolled, and started for this Windows server."
