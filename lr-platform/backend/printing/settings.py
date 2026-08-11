from __future__ import annotations

import threading
import logging
from dataclasses import asdict, dataclass, replace
from typing import Any

from backend.core.config import settings as app_settings
from backend.extensions import db


ALLOWED_DEFAULT_MODES = {"ask", "default", "preview", "save"}
ALLOWED_PRINTING_MODES = {"ask", "default", "preview", "save", "selected"}


@dataclass(frozen=True)
class PrintingSettings:
    enabled: bool = True
    max_job_size_mb: int = 50
    job_timeout_seconds: int = 120
    temp_retention_seconds: int = 300
    default_mode: str = "ask"
    browser_fallback: bool = True
    chunk_size: int = 256 * 1024
    automatic_printing: bool = False
    allowed_modes: tuple[str, ...] = ("ask", "default", "preview", "save", "selected")

    @property
    def max_job_size_bytes(self) -> int:
        return self.max_job_size_mb * 1024 * 1024

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["allowed_modes"] = list(self.allowed_modes)
        return value


def defaults_from_environment() -> PrintingSettings:
    modes = tuple(
        item.strip().lower()
        for item in str(getattr(app_settings, "PRINTING_ALLOWED_MODES", "")).split(",")
        if item.strip().lower() in ALLOWED_PRINTING_MODES
    ) or PrintingSettings.allowed_modes
    return PrintingSettings(
        enabled=bool(app_settings.PRINTING_ENABLED),
        max_job_size_mb=int(app_settings.PRINTING_MAX_JOB_SIZE_MB),
        job_timeout_seconds=int(app_settings.PRINTING_JOB_TIMEOUT_SECONDS),
        temp_retention_seconds=int(app_settings.PRINTING_TEMP_RETENTION_SECONDS),
        default_mode=str(app_settings.PRINTING_DEFAULT_MODE).lower(),
        browser_fallback=bool(app_settings.PRINTING_BROWSER_FALLBACK),
        chunk_size=int(app_settings.PRINTING_CHUNK_SIZE),
        automatic_printing=bool(app_settings.PRINTING_AUTOMATIC),
        allowed_modes=modes,
    )


class PrintingSettingsStore:
    """Runtime printing configuration backed by the existing Mongo database."""

    def __init__(self) -> None:
        self._value = defaults_from_environment()
        self._values = {}
        self._lock = threading.RLock()
        self._loaded = False

    def get(self, *, reload: bool = False, tenant_id=None) -> PrintingSettings:
        with self._lock:
            tenant_key = str(tenant_id or "")
            if reload or tenant_key not in self._values:
                try:
                    setting_id = f"printing:{tenant_key}" if tenant_key else "printing"
                    stored = db["system_settings"].find_one({"_id": setting_id}) or {}
                    if not stored and tenant_key:
                        stored = db["system_settings"].find_one({"_id": "printing"}) or {}
                    if stored:
                        self._values[tenant_key] = self._validated(stored, base=self._value)
                except Exception as error:
                    # Environment defaults remain operational if Mongo is temporarily unavailable.
                    logging.getLogger("lr_remote_access.printing.settings").warning(
                        "printing_settings_load_failed reason=%s", error
                    )
                self._values.setdefault(tenant_key, self._value)
                self._loaded = True
            return self._values[tenant_key]

    def update(self, values: Any, tenant_id=None) -> PrintingSettings:
        if not isinstance(values, dict):
            raise ValueError("Printing settings must be a JSON object")
        with self._lock:
            tenant_key = str(tenant_id or "")
            updated = self._validated(values, base=self.get(tenant_id=tenant_id))
            db["system_settings"].update_one(
                {"_id": f"printing:{tenant_key}" if tenant_key else "printing"},
                {"$set": {**updated.to_dict(), "tenant_id": tenant_key or None}},
                upsert=True,
            )
            self._value = updated
            self._values[tenant_key] = updated
            self._loaded = True
            return updated

    @staticmethod
    def _validated(values: dict[str, Any], *, base: PrintingSettings) -> PrintingSettings:
        allowed = set(base.to_dict())
        unknown = set(values) - allowed - {"_id", "tenant_id"}
        if unknown:
            raise ValueError(f"Unknown printing setting(s): {', '.join(sorted(unknown))}")
        payload = {key: values.get(key, getattr(base, key)) for key in allowed}
        for name in ("enabled", "browser_fallback", "automatic_printing"):
            if not isinstance(payload[name], bool):
                raise ValueError(f"{name} must be a boolean")
        limits = {
            "max_job_size_mb": (1, 1024),
            "job_timeout_seconds": (10, 3600),
            "temp_retention_seconds": (0, 86400),
            "chunk_size": (64 * 1024, 4 * 1024 * 1024),
        }
        for name, (minimum, maximum) in limits.items():
            try:
                payload[name] = int(payload[name])
            except (TypeError, ValueError) as error:
                raise ValueError(f"{name} must be an integer") from error
            if not minimum <= payload[name] <= maximum:
                raise ValueError(f"{name} must be between {minimum} and {maximum}")
        payload["default_mode"] = str(payload["default_mode"]).lower()
        if payload["default_mode"] not in ALLOWED_DEFAULT_MODES:
            raise ValueError("default_mode must be ask, default, preview, or save")
        modes = payload["allowed_modes"]
        if not isinstance(modes, (list, tuple)) or not modes:
            raise ValueError("allowed_modes must be a non-empty list")
        normalized_modes = tuple(dict.fromkeys(str(item).lower() for item in modes))
        if any(item not in ALLOWED_PRINTING_MODES for item in normalized_modes):
            raise ValueError("allowed_modes contains an unsupported mode")
        payload["allowed_modes"] = normalized_modes
        return replace(base, **payload)
