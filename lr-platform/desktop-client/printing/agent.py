from __future__ import annotations

import hashlib
import hmac
import os
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import quote, urlencode

from printing.providers import (
    WindowsAssociatedPdfPrintProvider,
    get_default_printer,
    list_local_printers,
    preview_pdf,
    save_pdf,
)
from printing.settings import ClientPrintSettingsStore


class PrintAgent:
    """Background authenticated PDF receiver for one exact RDP session."""

    def __init__(
        self,
        connection,
        settings_store: ClientPrintSettingsStore,
        ui_dispatcher: Callable[..., None],
        job_handler: Callable[["PrintAgent", dict[str, Any], str], None],
        status_handler: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.connection = connection
        self.settings_store = settings_store
        self.ui_dispatcher = ui_dispatcher
        self.job_handler = job_handler
        self.status_handler = status_handler
        self.connection_id = str(uuid.uuid4())
        self.session_id = ""
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._active_jobs: set[str] = set()
        self._lock = threading.RLock()
        base = Path(os.getenv("LOCALAPPDATA") or tempfile.gettempdir())
        self.temp_root = base / "LR Remote Access" / "PrintJobs" / self.connection_id
        self.provider = WindowsAssociatedPdfPrintProvider()

    def start(self, session_id: str) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.session_id = str(session_id)
        self._stop_event.clear()
        self.temp_root.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.temp_root.chmod(0o700)
        self._thread = threading.Thread(target=self._run, name="lr-print-agent", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        try:
            query = urlencode({"session_id": self.session_id})
            self.connection.delete_json(f"/api/printing/clients/{self.connection_id}?{query}")
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._cleanup_all()

    def list_printers(self) -> list[str]:
        return list_local_printers()

    def print_to_default(self, pdf_path: str, copies: int = 1) -> None:
        printer = get_default_printer()
        if not printer:
            raise RuntimeError("No default local printer is configured")
        self.provider.print_pdf(pdf_path, printer, copies)

    def print_to_selected(self, pdf_path: str, printer_name: str, copies: int = 1) -> None:
        self.provider.print_pdf(pdf_path, printer_name, copies)

    def preview(self, pdf_path: str) -> None:
        preview_pdf(pdf_path)

    def save_as(self, pdf_path: str, destination: str) -> None:
        save_pdf(pdf_path, destination)

    def perform_action(
        self,
        metadata: dict[str, Any],
        pdf_path: str,
        action: str,
        *,
        printer_name: str = "",
        copies: Optional[int] = None,
        destination: str = "",
        completion: Optional[Callable[[bool, str], None]] = None,
    ) -> None:
        def worker() -> None:
            try:
                chosen_copies = int(copies or metadata.get("copies") or 1)
                if action in {"default", "selected"}:
                    self._report(metadata, "printing")
                if action == "default":
                    self.print_to_default(pdf_path, chosen_copies)
                    final_state = "printed"
                elif action == "selected":
                    self.print_to_selected(pdf_path, printer_name, chosen_copies)
                    final_state = "printed"
                elif action == "preview":
                    self.preview(pdf_path)
                    final_state = "saved"
                elif action == "save":
                    self.save_as(pdf_path, destination)
                    final_state = "saved"
                elif action == "cancel":
                    final_state = "cancelled"
                else:
                    raise ValueError("Unknown print action")
                self._report(metadata, final_state)
                self._finish_local_job(metadata, pdf_path)
                message = "Print job completed" if final_state == "printed" else final_state.title()
                if completion:
                    self.ui_dispatcher(completion, True, message)
            except Exception as error:
                self._report(metadata, "failed", str(error))
                if completion:
                    self.ui_dispatcher(completion, False, str(error))

        threading.Thread(target=worker, name="lr-print-action", daemon=True).start()

    def _run(self) -> None:
        settings = self.settings_store.load()
        if not settings.enabled:
            return
        registered = False
        while not self._stop_event.is_set():
            try:
                if not registered:
                    self.connection.post_json("/api/printing/clients/register", {
                        "session_id": self.session_id,
                        "connection_id": self.connection_id,
                        "client_type": "desktop",
                        "capabilities": {
                            "binary_chunks": True,
                            "preview": True,
                            "save": True,
                            "named_printers": os.name == "nt",
                        },
                        "printers": self.list_printers(),
                    })
                    registered = True
                    self._status("Remote printing ready")
                query = urlencode({"session_id": self.session_id, "wait": 25})
                result = self.connection.get_json(
                    f"/api/printing/clients/{self.connection_id}/next?{query}",
                    timeout=35,
                )
                metadata = result.get("job") if isinstance(result, dict) else None
                if metadata:
                    self.receive_job(metadata)
            except Exception as error:
                registered = False
                self._status(f"Remote printing reconnecting: {error}")
                self._stop_event.wait(5.0)

    def receive_job(self, metadata: dict[str, Any]) -> None:
        job_id = str(metadata.get("job_id") or "")
        if str(metadata.get("session_id") or "") != self.session_id:
            raise PermissionError("Server offered a print job for a different session")
        try:
            uuid.UUID(job_id)
        except ValueError as error:
            raise ValueError("Server offered an invalid print-job ID") from error
        with self._lock:
            if job_id in self._active_jobs:
                return
            self._active_jobs.add(job_id)
        try:
            pdf_path = self._download_job(metadata)
            self._report(metadata, "received")
            settings = self.settings_store.load()
            if settings.show_notification:
                self._status(
                    f"Remote print job received: {str(metadata.get('document_name') or 'Document')[:80]}"
                )
            if settings.default_action == "ask":
                self._report(metadata, "awaiting_user")
                self.ui_dispatcher(self.job_handler, self, metadata, str(pdf_path))
            else:
                action = settings.default_action
                destination = ""
                if action == "save":
                    self._report(metadata, "awaiting_user")
                    self.ui_dispatcher(self.job_handler, self, metadata, str(pdf_path))
                else:
                    self.perform_action(
                        metadata,
                        str(pdf_path),
                        action,
                        printer_name=settings.preferred_printer,
                    )
        except Exception as error:
            self._report(metadata, "failed", str(error))
            with self._lock:
                self._active_jobs.discard(job_id)
            raise

    def _download_job(self, metadata: dict[str, Any]) -> Path:
        size = int(metadata.get("size") or 0)
        expected_hash = str(metadata.get("sha256") or "").lower()
        if size <= 0 or len(expected_hash) != 64:
            raise ValueError("Print-job metadata is invalid")
        maximum = 1024 * 1024 * 1024
        if size > maximum:
            raise ValueError("Print job exceeds the client safety limit")
        temporary = self.temp_root / f".{metadata['job_id']}.{uuid.uuid4().hex}.part"
        final_path = self.temp_root / f"{metadata['job_id']}.pdf"
        digest = hashlib.sha256()
        received = 0
        sequence = 0
        started = time.monotonic()
        settings = self.settings_store.load()
        try:
            with temporary.open("xb") as handle:
                if os.name != "nt":
                    temporary.chmod(0o600)
                while received < size:
                    if self._stop_event.is_set():
                        raise RuntimeError("Print transfer was cancelled")
                    if time.monotonic() - started > settings.job_timeout_seconds:
                        raise TimeoutError("Print-job transfer timed out")
                    query = urlencode({
                        "session_id": self.session_id,
                        "connection_id": self.connection_id,
                    })
                    chunk, headers = self.connection.get_binary(
                        f"/api/printing/jobs/{quote(str(metadata['job_id']))}/chunks/{sequence}?{query}"
                    )
                    returned_sequence = int(headers.get("X-Print-Chunk-Sequence", "-1"))
                    offset = int(headers.get("X-Print-Chunk-Offset", "-1"))
                    if returned_sequence != sequence or offset != received:
                        raise ValueError("Print-job chunk sequence is invalid")
                    if not chunk or received + len(chunk) > size:
                        raise ValueError("Print-job chunk size is invalid")
                    handle.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    sequence += 1
                handle.flush()
                os.fsync(handle.fileno())
            if received != size:
                raise ValueError("Print-job size verification failed")
            if not hmac.compare_digest(digest.hexdigest(), expected_hash):
                raise ValueError("Print-job SHA-256 verification failed")
            os.replace(temporary, final_path)
            return final_path
        finally:
            temporary.unlink(missing_ok=True)

    def _report(self, metadata: dict[str, Any], state: str, error: str | None = None) -> None:
        try:
            self.connection.post_json(
                f"/api/printing/jobs/{quote(str(metadata.get('job_id') or ''))}/result",
                {
                    "session_id": self.session_id,
                    "connection_id": self.connection_id,
                    "state": state,
                    "error": str(error)[:500] if error else None,
                },
            )
        except Exception:
            if state not in {"failed", "cancelled"}:
                raise

    def _finish_local_job(self, metadata: dict[str, Any], pdf_path: str) -> None:
        job_id = str(metadata.get("job_id") or "")
        settings = self.settings_store.load()
        with self._lock:
            self._active_jobs.discard(job_id)
        if settings.auto_remove_temp_files:
            timer = threading.Timer(
                settings.temp_retention_seconds,
                lambda: Path(pdf_path).unlink(missing_ok=True),
            )
            timer.daemon = True
            timer.start()

    def _cleanup_all(self) -> None:
        try:
            shutil.rmtree(self.temp_root)
        except FileNotFoundError:
            pass
        except OSError:
            pass

    def _status(self, text: str) -> None:
        if self.status_handler:
            self.ui_dispatcher(self.status_handler, text)


class PrintAgentManager:
    def __init__(self, root, settings_store, job_handler, status_handler=None) -> None:
        self.root = root
        self.settings_store = settings_store
        self.job_handler = job_handler
        self.status_handler = status_handler
        self._agents: dict[str, PrintAgent] = {}
        self._lock = threading.RLock()

    def start_session(self, connection, session_id: str) -> PrintAgent:
        with self._lock:
            existing = self._agents.get(str(session_id))
            if existing:
                return existing
            agent = PrintAgent(
                connection,
                self.settings_store,
                self._dispatch,
                self.job_handler,
                self.status_handler,
            )
            self._agents[str(session_id)] = agent
            agent.start(str(session_id))
            return agent

    def stop_all(self) -> None:
        with self._lock:
            agents = list(self._agents.values())
            self._agents.clear()
        for agent in agents:
            agent.stop()

    def stop_session(self, session_id: str) -> None:
        with self._lock:
            agent = self._agents.pop(str(session_id), None)
        if agent:
            agent.stop()

    def _dispatch(self, callback, *args) -> None:
        self.root.after(0, callback, *args)
