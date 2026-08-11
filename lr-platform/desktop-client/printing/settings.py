from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


PRINT_ACTIONS = {"ask", "default", "preview", "save"}


@dataclass
class ClientPrintSettings:
    enabled: bool = True
    default_action: str = "ask"
    preferred_printer: str = ""
    show_notification: bool = True
    auto_remove_temp_files: bool = True
    job_timeout_seconds: int = 120
    temp_retention_seconds: int = 300

    @classmethod
    def from_dict(cls, value: Any) -> "ClientPrintSettings":
        data = value if isinstance(value, dict) else {}
        action = str(data.get("default_action") or "ask").lower()
        if action not in PRINT_ACTIONS:
            action = "ask"
        try:
            timeout = min(max(int(data.get("job_timeout_seconds", 100)), 5), 3600)
            retention = min(max(int(data.get("temp_retention_seconds", 300)), 30), 86400)
        except (TypeError, ValueError):
            timeout, retention = 120, 300
        return cls(
            enabled=bool(data.get("enabled", True)),
            default_action=action,
            preferred_printer=str(data.get("preferred_printer") or "")[:256],
            show_notification=bool(data.get("show_notification", True)),
            auto_remove_temp_files=bool(data.get("auto_remove_temp_files", True)),
            job_timeout_seconds=timeout,
            temp_retention_seconds=retention,
        )


class ClientPrintSettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        local = Path(os.getenv("LOCALAPPDATA") or Path.home())
        self.path = path or local / "LR Remote Access" / "printing.json"
        self._lock = threading.RLock()

    def load(self) -> ClientPrintSettings:
        with self._lock:
            try:
                return ClientPrintSettings.from_dict(
                    json.loads(self.path.read_text(encoding="utf-8"))
                )
            except (OSError, UnicodeError, json.JSONDecodeError):
                return ClientPrintSettings()

    def save(self, value: ClientPrintSettings) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(asdict(value), indent=2, sort_keys=True), encoding="utf-8"
            )
            os.replace(temporary, self.path)
