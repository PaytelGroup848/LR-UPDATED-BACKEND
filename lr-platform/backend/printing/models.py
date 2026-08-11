from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


PRINT_JOB_STATES = {
    "created",
    "generating",
    "ready",
    "transferring",
    "received",
    "awaiting_user",
    "printing",
    "printed",
    "saved",
    "cancelled",
    "failed",
    "expired",
}
TERMINAL_PRINT_JOB_STATES = {"printed", "saved", "cancelled", "failed", "expired"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PrintJob:
    """A PDF print job bound to one authenticated LR session and connection."""

    job_id: str
    session_id: str
    user_id: str
    document_name: str
    pdf_path: Path
    file_size: int
    sha256: str
    tenant_id: Optional[str] = None
    copies: int = 1
    color: bool = True
    duplex: bool = False
    requested_printer: Optional[str] = None
    connection_id: Optional[str] = None
    client_type: str = "desktop"
    state: str = "created"
    error: Optional[str] = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    expires_at: Optional[datetime] = None
    sidecar_path: Optional[Path] = None
    download_token_hash: Optional[str] = None
    download_token_expires_at: Optional[datetime] = None
    download_token_used: bool = False

    def set_state(self, state: str, error: Optional[str] = None) -> None:
        if state not in PRINT_JOB_STATES:
            raise ValueError(f"Unknown print-job state: {state}")
        self.state = state
        self.error = error
        self.updated_at = utcnow()

    def metadata(self, *, admin: bool = False) -> dict[str, Any]:
        payload = {
            "job_id": self.job_id,
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "document_name": self.document_name,
            "content_type": "application/pdf",
            "size": self.file_size,
            "sha256": self.sha256,
            "copies": self.copies,
            "color": self.color,
            "duplex": self.duplex,
            "requested_printer": self.requested_printer,
            "state": self.state,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "error": self.error,
        }
        if admin:
            payload.update({
                "user_id": self.user_id,
                "connection_id": self.connection_id,
                "client_type": self.client_type,
            })
        return payload


@dataclass(frozen=True)
class CaptureMetadata:
    """Validated metadata read from a watched-folder JSON sidecar."""

    session_id: str
    user_id: str
    document_name: str
    copies: int = 1
    color: bool = True
    duplex: bool = False
    requested_printer: Optional[str] = None
    connection_id: Optional[str] = None

    @classmethod
    def from_dict(cls, value: Any) -> "CaptureMetadata":
        if not isinstance(value, dict):
            raise ValueError("Print metadata must be a JSON object")
        session_id = _required_identifier(value.get("session_id"), "session_id")
        user_id = _required_identifier(value.get("user_id"), "user_id")
        connection_id = value.get("connection_id")
        if connection_id is not None:
            connection_id = _required_identifier(connection_id, "connection_id", max_length=128)
        document_name = sanitize_document_name(value.get("document_name"))
        try:
            copies = int(value.get("copies", 1))
        except (TypeError, ValueError) as error:
            raise ValueError("copies must be an integer") from error
        if not 1 <= copies <= 99:
            raise ValueError("copies must be between 1 and 99")
        requested_printer = value.get("requested_printer")
        if requested_printer is not None:
            requested_printer = str(requested_printer).strip()
            if not requested_printer or len(requested_printer) > 256 or any(
                char in requested_printer for char in "\r\n\0"
            ):
                raise ValueError("requested_printer is invalid")
        return cls(
            session_id=session_id,
            user_id=user_id,
            document_name=document_name,
            copies=copies,
            color=_strict_bool(value.get("color", True), "color"),
            duplex=_strict_bool(value.get("duplex", False), "duplex"),
            requested_printer=requested_printer,
            connection_id=connection_id,
        )


def _required_identifier(value: Any, name: str, max_length: int = 256) -> str:
    text = str(value or "").strip()
    if not text or len(text) > max_length or any(char in text for char in "\r\n\0/\\"):
        raise ValueError(f"{name} is invalid")
    return text


def _strict_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def sanitize_document_name(value: Any) -> str:
    """Return a display-only document name with path/control characters removed."""

    text = str(value or "Document").replace("\\", "_").replace("/", "_")
    text = "".join(char for char in text if char.isprintable() and char not in "\r\n\0")
    text = " ".join(text.split()).strip(" .")
    return (text[:160] or "Document")
