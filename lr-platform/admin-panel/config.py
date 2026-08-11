import json
import os
from pathlib import Path

try:
    from build_version import APP_VERSION
except ImportError:
    APP_VERSION = "0.0.0-dev"


APP_ID = "admin-panel"
APP_NAME = "Admin Panel"
DEFAULT_BACKEND_URL = os.getenv('LR_BACKEND_URL', 'http://191.44.87.38:8004')


class SettingsStore:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv('LR_ADMIN_SETTINGS') or Path.home() / '.lr_admin_panel.json')

    def load(self):
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return {}

    def save(self, values):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(values, indent=2, sort_keys=True), encoding='utf-8')
