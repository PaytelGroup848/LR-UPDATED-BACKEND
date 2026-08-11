import json
import os
from pathlib import Path


def state_directory():
    configured = str(os.getenv("LR_AGENT_STATE_DIR") or "").strip()
    if configured:
        return Path(configured)
    if os.name == "nt":
        root = Path(os.getenv("PROGRAMDATA") or r"C:\ProgramData")
        return root / "LR Remote Access" / "Agent"
    return Path(__file__).resolve().parent / "state"


def bootstrap_path():
    return state_directory() / "bootstrap.json"


def load_bootstrap():
    try:
        value = json.loads(bootstrap_path().read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def clear_enrollment_token():
    path = bootstrap_path()
    data = load_bootstrap()
    if not data or not data.get("enrollment_token"):
        return
    data["enrollment_token"] = None
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
