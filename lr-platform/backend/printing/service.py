from __future__ import annotations

import hashlib
import hmac
import atexit
import secrets
import threading
import time
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

from backend.core.config import PROJECT_DIR, settings as app_settings
from backend.manager.logger import get_logger
from backend.models.rdp_session import RdpSession
from backend.printing.models import (
    CaptureMetadata,
    PrintJob,
    TERMINAL_PRINT_JOB_STATES,
    sanitize_document_name,
    utcnow,
)
from backend.printing.registry import PrintClientRegistration, SessionRegistry
from backend.printing.settings import PrintingSettingsStore


CLIENT_RESULT_STATES = {
    "received", "awaiting_user", "printing", "printed", "saved", "cancelled", "failed"
}


def _id_matches(value: Any, expected: str) -> bool:
    return str(value or "") == str(expected)


class PrintJobService:
    """Capture, route, transfer, track, and clean secure remote print jobs."""

    def __init__(
        self,
        *,
        registry: Optional[SessionRegistry] = None,
        settings_store: Optional[PrintingSettingsStore] = None,
        capture_root: Optional[Path] = None,
        session_lookup=None,
    ) -> None:
        self.registry = registry or SessionRegistry()
        self.settings = settings_store or PrintingSettingsStore()
        self.capture_root = Path(
            capture_root
            or app_settings.PRINTING_SPOOL_ROOT
            or Path(PROJECT_DIR) / "data" / "print_jobs"
        ).resolve()
        self._session_lookup = session_lookup or self._default_session_lookup
        self._jobs: dict[str, PrintJob] = {}
        self._lock = threading.RLock()
        self._job_ready = threading.Condition(self._lock)
        self._capture = None
        self._started = False
        self._logger = get_logger("lr_remote_access.printing")

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            from backend.printing.capture import WatchedFolderPrintCaptureProvider

            self._capture = WatchedFolderPrintCaptureProvider(self, self.capture_root)
            self._capture.start()
            self._started = True
            self._logger.info("print_service_started spool_root=%s", self.capture_root)

    def stop(self) -> None:
        with self._lock:
            capture = self._capture
            self._started = False
        if capture:
            capture.stop()

    def register_client(
        self,
        *,
        session_id: str,
        connection_id: str,
        user_id: str,
        client_type: str,
        capabilities: dict[str, Any],
        printers: list[str],
        tenant_id: Optional[str] = None,
    ) -> PrintClientRegistration:
        config = self.settings.get(tenant_id=tenant_id)
        if not config.enabled:
            raise PermissionError("Remote printing is disabled")
        session = self._authorize_session(session_id, user_id)
        if tenant_id is not None and str(session.get("tenant_id") or "") != str(tenant_id):
            raise PermissionError("Remote session belongs to another tenant")
        if str(session.get("status") or "") not in {"active", "pending"}:
            raise PermissionError("Remote session is not active")
        if client_type not in {"desktop", "browser"}:
            raise ValueError("client_type must be desktop or browser")
        if client_type == "browser" and not config.browser_fallback:
            raise PermissionError("Browser printing fallback is disabled")
        try:
            uuid.UUID(str(connection_id))
        except ValueError as error:
            raise ValueError("connection_id must be a UUID") from error
        safe_printers = self._validate_printer_list(printers)
        return self.registry.register_print_client(
            session_id,
            connection_id,
            user_id,
            client_type=client_type,
            capabilities=capabilities,
            printers=safe_printers,
            tenant_id=tenant_id,
        )

    def unregister_client(self, session_id: str, connection_id: str, user_id: str, tenant_id=None) -> bool:
        registration = self.registry.get_print_client(
            session_id, connection_id, user_id=user_id, tenant_id=tenant_id
        )
        if not registration:
            return False
        removed = self.registry.unregister_print_client(session_id, connection_id, tenant_id)
        if removed:
            with self._job_ready:
                for job in self._jobs.values():
                    if job.connection_id == connection_id and job.state not in TERMINAL_PRINT_JOB_STATES:
                        job.set_state("failed", "Print client disconnected")
                        self.cleanup_job(job.job_id, force=True)
                self._job_ready.notify_all()
        return removed

    def submit_captured_job(
        self,
        job_id: str,
        pdf_path: Path,
        sidecar_path: Path,
        metadata: CaptureMetadata,
    ) -> PrintJob:
        try:
            parsed_id = str(uuid.UUID(str(job_id)))
        except ValueError as error:
            raise ValueError("job_id must be a UUID") from error
        if parsed_id != str(job_id).lower():
            raise ValueError("job_id must use canonical UUID form")
        config = self.settings.get()
        if not config.enabled:
            raise PermissionError("Remote printing is disabled")
        session = self._authorize_session(metadata.session_id, metadata.user_id)
        tenant_id = str(session.get("tenant_id") or "")
        if str(session.get("status") or "") not in {"active", "pending"}:
            raise PermissionError("Remote session is not active")
        registration = self.registry.get_print_client(
            metadata.session_id,
            metadata.connection_id,
            user_id=metadata.user_id,
            tenant_id=tenant_id,
        )
        if not registration:
            count = self.registry.count_for_session(metadata.session_id, metadata.user_id, tenant_id)
            if count > 1 and not metadata.connection_id:
                raise RuntimeError("Multiple print clients are registered; connection_id is required")
            raise RuntimeError("No print-capable client is registered for this session")
        file_size = pdf_path.stat().st_size
        if file_size > config.max_job_size_bytes:
            raise ValueError("PDF exceeds the configured maximum print-job size")
        digest = self._sha256(pdf_path)
        job = PrintJob(
            job_id=parsed_id,
            session_id=metadata.session_id,
            user_id=metadata.user_id,
            document_name=sanitize_document_name(metadata.document_name),
            pdf_path=pdf_path.resolve(),
            file_size=file_size,
            sha256=digest,
            tenant_id=tenant_id,
            copies=metadata.copies,
            color=metadata.color,
            duplex=metadata.duplex,
            requested_printer=metadata.requested_printer,
            connection_id=registration.connection_id,
            client_type=registration.client_type,
            sidecar_path=sidecar_path.resolve(),
            expires_at=utcnow() + timedelta(seconds=config.job_timeout_seconds),
        )
        job.set_state("ready")
        self.submit_job(job)
        self._logger.info(
            "print_job_ready job_id=%s session=%s connection=%s size=%s",
            job.job_id,
            job.session_id[:12],
            job.connection_id[:12] if job.connection_id else "none",
            job.file_size,
        )
        return job

    def submit_job(self, job: PrintJob) -> None:
        with self._job_ready:
            if job.job_id in self._jobs:
                raise ValueError("Duplicate print-job ID")
            self._jobs[job.job_id] = job
            self._job_ready.notify_all()

    def record_capture_failure(
        self, job_id: str, metadata: CaptureMetadata, reason: str
    ) -> PrintJob:
        failed_path = self.capture_root / "failed" / f"{job_id}.pdf"
        job = PrintJob(
            job_id=str(job_id),
            session_id=metadata.session_id,
            user_id=metadata.user_id,
            document_name=sanitize_document_name(metadata.document_name),
            pdf_path=failed_path,
            file_size=failed_path.stat().st_size if failed_path.exists() else 0,
            sha256=self._sha256(failed_path) if failed_path.exists() else "",
            connection_id=metadata.connection_id,
        )
        job.set_state("failed", str(reason)[:500])
        with self._lock:
            self._jobs.setdefault(job.job_id, job)
        return job

    def claim_next_job(
        self,
        session_id: str,
        connection_id: str,
        user_id: str,
        *,
        wait_seconds: float = 0,
        tenant_id: Optional[str] = None,
    ) -> Optional[PrintJob]:
        registration = self.registry.get_print_client(
            session_id, connection_id, user_id=user_id, tenant_id=tenant_id
        )
        if not registration:
            raise PermissionError("Print client registration was not found")
        self.registry.heartbeat(session_id, connection_id, user_id, tenant_id)
        self.expire_and_cleanup()
        timeout = min(max(float(wait_seconds or 0), 0.0), 25.0)
        deadline = time.monotonic() + timeout
        with self._job_ready:
            while True:
                candidates = [
                    job for job in self._jobs.values()
                    if job.session_id == str(session_id)
                    and job.connection_id == str(connection_id)
                    and job.user_id == str(user_id)
                    and (tenant_id is None or job.tenant_id == str(tenant_id))
                    and job.state in {"ready", "transferring"}
                ]
                if candidates:
                    job = min(candidates, key=lambda item: item.created_at)
                    if job.state == "ready":
                        job.set_state("transferring")
                    return job
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._job_ready.wait(remaining)
                if not self.registry.get_print_client(
                    session_id, connection_id, user_id=user_id, tenant_id=tenant_id
                ):
                    return None

    def get_chunk(
        self,
        job_id: str,
        sequence: int,
        *,
        session_id: str,
        connection_id: str,
        user_id: str,
        tenant_id: Optional[str] = None,
    ) -> tuple[bytes, int, bool]:
        job = self._authorized_job(job_id, session_id, connection_id, user_id, tenant_id)
        self._ensure_transferable(job)
        config = self.settings.get()
        if sequence < 0:
            raise ValueError("Chunk sequence must be non-negative")
        offset = sequence * config.chunk_size
        if offset >= job.file_size:
            raise ValueError("Chunk sequence is outside the print job")
        with job.pdf_path.open("rb") as handle:
            handle.seek(offset)
            data = handle.read(config.chunk_size)
        if not data:
            raise IOError("Print-job chunk could not be read")
        return data, offset, offset + len(data) == job.file_size

    def report_result(
        self,
        job_id: str,
        state: str,
        *,
        session_id: str,
        connection_id: str,
        user_id: str,
        error: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> PrintJob:
        if state not in CLIENT_RESULT_STATES:
            raise ValueError("Invalid print-job result state")
        job = self._authorized_job(job_id, session_id, connection_id, user_id, tenant_id)
        with self._lock:
            if job.state in TERMINAL_PRINT_JOB_STATES:
                if job.state == state:
                    return job
                raise RuntimeError(f"Print job is already {job.state}")
            job.set_state(state, str(error)[:500] if error else None)
        if state in TERMINAL_PRINT_JOB_STATES:
            self.cleanup_job(job.job_id, force=True)
        self._logger.info(
            "print_job_result job_id=%s session=%s state=%s reason=%s",
            job.job_id,
            job.session_id[:12],
            job.state,
            job.error or "none",
        )
        return job

    def cancel_job(
        self,
        job_id: str,
        *,
        user_id: Optional[str] = None,
        admin: bool = False,
        tenant_id: Optional[str] = None,
    ) -> PrintJob:
        with self._lock:
            job = self._jobs.get(str(job_id))
            if not job:
                raise KeyError("Print job not found")
            if not admin and job.user_id != str(user_id):
                raise PermissionError("Print job belongs to another user")
            if tenant_id is not None and job.tenant_id != str(tenant_id):
                raise PermissionError("Print job belongs to another tenant")
            if job.state not in TERMINAL_PRINT_JOB_STATES:
                job.set_state("cancelled")
        self.cleanup_job(job.job_id, force=True)
        return job

    def cleanup_job(self, job_id: str, *, force: bool = False) -> bool:
        with self._lock:
            job = self._jobs.get(str(job_id))
            if not job:
                return False
            if not force and job.state not in TERMINAL_PRINT_JOB_STATES:
                return False
            paths = [job.pdf_path, job.sidecar_path]
        removed = False
        for path in paths:
            if path and path.exists():
                try:
                    resolved = path.resolve()
                    resolved.relative_to(self.capture_root)
                    resolved.unlink()
                    removed = True
                except (OSError, ValueError):
                    self._logger.exception("print_cleanup_failed job_id=%s", job_id)
        return removed

    def expire_and_cleanup(self) -> int:
        now = utcnow()
        config = self.settings.get()
        cutoff = now - timedelta(seconds=max(config.job_timeout_seconds, 30))
        stale_clients = self.registry.remove_stale(cutoff)
        stale_connections = {client.connection_id for client in stale_clients}
        expired = 0
        with self._lock:
            for job in self._jobs.values():
                if job.state not in TERMINAL_PRINT_JOB_STATES and (
                    (job.expires_at and now >= job.expires_at)
                    or job.connection_id in stale_connections
                ):
                    job.set_state("expired", "Print-job transfer timed out")
                    expired += 1
                terminal_age = (now - job.updated_at).total_seconds()
                if job.state in TERMINAL_PRINT_JOB_STATES and terminal_age >= config.temp_retention_seconds:
                    self.cleanup_job(job.job_id, force=True)
        return expired

    def issue_browser_download_token(self, job: PrintJob) -> str:
        if job.client_type != "browser":
            raise PermissionError("Print job is not registered to a browser client")
        token = secrets.token_urlsafe(32)
        job.download_token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        job.download_token_expires_at = utcnow() + timedelta(seconds=min(120, self.settings.get().job_timeout_seconds))
        job.download_token_used = False
        return token

    def consume_browser_download(
        self, job_id: str, token: str, user_id: str, tenant_id: Optional[str] = None
    ) -> PrintJob:
        with self._lock:
            job = self._jobs.get(str(job_id))
            if (
                not job or job.user_id != str(user_id) or job.client_type != "browser"
                or (tenant_id is not None and job.tenant_id != str(tenant_id))
            ):
                raise PermissionError("Print download is not authorized")
            digest = hashlib.sha256(str(token).encode("utf-8")).hexdigest()
            if (
                job.download_token_used
                or not job.download_token_hash
                or not hmac.compare_digest(digest, job.download_token_hash)
                or not job.download_token_expires_at
                or utcnow() >= job.download_token_expires_at
            ):
                raise PermissionError("Print download token is invalid or expired")
            job.download_token_used = True
            job.set_state("received")
            return job

    def list_jobs(self, *, user_id: Optional[str] = None, tenant_id: Optional[str] = None) -> list[dict[str, Any]]:
        with self._lock:
            jobs = [
                job for job in self._jobs.values()
                if user_id is None or job.user_id == str(user_id)
                if tenant_id is None or job.tenant_id == str(tenant_id)
            ]
            return [job.metadata(admin=user_id is None) for job in sorted(
                jobs, key=lambda item: item.created_at, reverse=True
            )]

    def get_job(self, job_id: str) -> Optional[PrintJob]:
        with self._lock:
            return self._jobs.get(str(job_id))

    def clear_expired(self, tenant_id=None) -> int:
        with self._lock:
            ids = [
                job.job_id for job in self._jobs.values()
                if job.state == "expired" and (tenant_id is None or job.tenant_id == str(tenant_id))
            ]
        for job_id in ids:
            self.cleanup_job(job_id, force=True)
            with self._lock:
                self._jobs.pop(job_id, None)
        return len(ids)

    def _authorized_job(
        self, job_id: str, session_id: str, connection_id: str, user_id: str, tenant_id=None
    ) -> PrintJob:
        with self._lock:
            job = self._jobs.get(str(job_id))
            if not job:
                raise KeyError("Unknown or expired print job")
            if not (
                job.session_id == str(session_id)
                and job.connection_id == str(connection_id)
                and job.user_id == str(user_id)
                and (tenant_id is None or job.tenant_id == str(tenant_id))
            ):
                raise PermissionError("Print job belongs to a different session or client")
            return job

    @staticmethod
    def _ensure_transferable(job: PrintJob) -> None:
        if job.expires_at and utcnow() >= job.expires_at:
            job.set_state("expired", "Print-job transfer timed out")
            raise RuntimeError("Print job has expired")
        if job.state not in {"ready", "transferring"}:
            raise RuntimeError(f"Print job is {job.state}")

    def _authorize_session(self, session_id: str, user_id: str) -> dict[str, Any]:
        session = self._session_lookup(str(session_id))
        if not session:
            raise PermissionError("Remote session was not found")
        if not _id_matches(session.get("user_id"), str(user_id)):
            raise PermissionError("Remote session belongs to another user")
        return session

    @staticmethod
    def _default_session_lookup(session_id: str) -> Optional[dict[str, Any]]:
        from bson import ObjectId

        try:
            object_id = ObjectId(str(session_id))
        except Exception:
            return None
        return RdpSession.collection.find_one({"_id": object_id})

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _validate_printer_list(printers: Any) -> list[str]:
        if not isinstance(printers, list):
            raise ValueError("printers must be a list")
        result = []
        for value in printers[:256]:
            name = str(value).strip()
            if name and len(name) <= 256 and not any(char in name for char in "\r\n\0"):
                result.append(name)
        return list(dict.fromkeys(result))


_service: Optional[PrintJobService] = None
_service_lock = threading.Lock()


def get_print_job_service() -> PrintJobService:
    global _service
    with _service_lock:
        if _service is None:
            _service = PrintJobService()
            atexit.register(_service.stop)
        return _service
