from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests

from backend.core.config import settings as app_settings


class LicenseServerUnavailable(RuntimeError):
    """Raised when the external license authority cannot be reached safely."""


@dataclass(frozen=True)
class ExternalLicenseValidation:
    expires_at: datetime
    status: str = "active"


class ExternalLicenseValidator:
    """Validate LR keys against the configured Super Admin license API."""

    def __init__(self, url: str | None = None, timeout_seconds: float | None = None):
        self.url = str(url or app_settings.LICENSE_VALIDATION_URL or "").strip()
        self.timeout_seconds = float(
            timeout_seconds or app_settings.LICENSE_VALIDATION_TIMEOUT_SECONDS
        )

    def validate(self, key_code: str) -> ExternalLicenseValidation:
        key_code = str(key_code or "").strip()
        if not key_code:
            raise ValueError("LR-Key is required")
        if not self.url:
            raise LicenseServerUnavailable("License validation URL is not configured")
        parsed_url = urlparse(self.url)
        internal_http = (
            parsed_url.scheme.lower() == "http"
            and parsed_url.hostname in {"license-authority", "localhost", "127.0.0.1", "::1"}
        )
        if parsed_url.scheme.lower() != "https" and not internal_http:
            raise LicenseServerUnavailable(
                "License validation URL must use HTTPS to protect the LR-Key."
            )

        try:
            response = requests.post(
                self.url,
                json={"key": key_code},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload: Any = response.json()
        except requests.exceptions.RequestException as error:
            raise LicenseServerUnavailable(
                "Could not reach the license server. Check the internet connection and try again."
            ) from error
        except (TypeError, ValueError) as error:
            raise LicenseServerUnavailable(
                "License server returned an invalid response. Please try again."
            ) from error

        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise LicenseServerUnavailable(
                "License server could not validate the key. Please try again."
            )

        data = payload.get("data")
        if not isinstance(data, dict):
            raise LicenseServerUnavailable("License server returned an invalid response.")

        status = str(data.get("status") or "invalid").strip().lower()
        if data.get("valid") is not True:
            messages = {
                "not_found": "LR-Key was not found.",
                "expired": "LR-Key has expired.",
                "suspended": "LR-Key is suspended.",
            }
            raise ValueError(messages.get(status, "LR-Key is invalid."))

        expires_at = self._parse_expiry(data.get("expiresAt"))
        if expires_at <= datetime.utcnow():
            raise ValueError("LR-Key has expired.")
        return ExternalLicenseValidation(expires_at=expires_at, status=status or "active")

    @staticmethod
    def _parse_expiry(value: Any) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise LicenseServerUnavailable(
                "License server did not return a valid expiry date."
            )
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as error:
            raise LicenseServerUnavailable(
                "License server returned an invalid expiry date."
            ) from error
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
