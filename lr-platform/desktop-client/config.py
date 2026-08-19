import os
import sys
from pathlib import Path

# Automatically load .env configuration (source or frozen PyInstaller executable)
if getattr(sys, "frozen", False):
    base_dir = Path(sys.executable).resolve().parent
else:
    base_dir = Path(__file__).resolve().parents[1]

env_paths = [
    base_dir / ".env",
    Path.cwd() / ".env",
    Path.home() / ".env",
]

for env_path in env_paths:
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path)
        except Exception:
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            os.environ.setdefault(k.strip(), v.strip().strip("'\""))
            except Exception:
                pass
        break

try:
    from build_version import APP_VERSION
except ImportError:
    APP_VERSION = "0.0.0-dev"

APP_ID = "desktop-client"
APP_NAME = "Desktop Client"
# Desktop clients connect through the public API gateway. Port 8004 belongs to
# the internal web-backend service and may not be exposed to client machines.
DEFAULT_SERVER_URL = os.getenv('LR_SERVER_URL', 'http://191.44.87.38:8004')
DEFAULT_COMPANY_CODE = os.getenv('LR_COMPANY_CODE', '')
