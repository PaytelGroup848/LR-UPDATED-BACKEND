from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, Optional

from backend.manager.logger import get_logger
from backend.printing.models import CaptureMetadata

if TYPE_CHECKING:
    from backend.printing.service import PrintJobService


class PrintCaptureProvider:
    """Interface for a server-side source of completed PDF print jobs."""

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def get_completed_jobs(self) -> Iterator[tuple[str, Path, Path, CaptureMetadata]]:
        raise NotImplementedError


class WatchedFolderPrintCaptureProvider(PrintCaptureProvider):
    """Capture PDFs and matching JSON metadata from an atomic watched folder."""

    def __init__(
        self,
        service: "PrintJobService",
        root: Path,
        *,
        poll_interval: float = 0.5,
        stability_seconds: float = 0.75,
    ) -> None:
        self.service = service
        self.root = Path(root).resolve()
        self.incoming = self.root / "incoming"
        self.processing = self.root / "processing"
        self.failed = self.root / "failed"
        self.poll_interval = poll_interval
        self.stability_seconds = stability_seconds
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._observed: dict[str, tuple[int, int, float]] = {}
        self._logger = get_logger("lr_remote_access.printing.capture")

    def start(self) -> None:
        self._ensure_directories()
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="lr-print-capture",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(2.0, self.poll_interval * 3))

    def get_completed_jobs(self) -> Iterator[tuple[str, Path, Path, CaptureMetadata]]:
        now = time.monotonic()
        for sidecar in sorted(self.incoming.glob("*.json")):
            job_id = sidecar.stem
            try:
                uuid.UUID(job_id)
            except ValueError:
                self._fail_incoming(job_id, "File name must be a UUID")
                continue
            pdf_path = self.incoming / f"{job_id}.pdf"
            if not pdf_path.is_file():
                continue
            try:
                stat = pdf_path.stat()
                metadata_stat = sidecar.stat()
            except OSError:
                continue
            signature = (stat.st_size, metadata_stat.st_size)
            previous = self._observed.get(job_id)
            if not previous or previous[:2] != signature:
                self._observed[job_id] = (*signature, now)
                continue
            if now - previous[2] < self.stability_seconds:
                continue
            self._observed.pop(job_id, None)
            try:
                metadata = self._read_metadata(sidecar)
                self._validate_pdf(pdf_path)
                processing_pdf, processing_sidecar = self._move_to_processing(
                    job_id, pdf_path, sidecar
                )
                yield job_id, processing_pdf, processing_sidecar, metadata
            except Exception as error:
                self._logger.warning("print_capture_rejected job_id=%s reason=%s", job_id, error)
                self._fail_incoming(job_id, str(error))

    def fail_processing(self, job_id: str, reason: str) -> None:
        self.failed.mkdir(parents=True, exist_ok=True)
        for suffix in (".pdf", ".json"):
            source = self.processing / f"{job_id}{suffix}"
            if source.exists():
                os.replace(source, self.failed / source.name)
        error_path = self.failed / f"{job_id}.error.json"
        error_path.write_text(
            json.dumps({"job_id": job_id, "error": str(reason)[:500]}, indent=2),
            encoding="utf-8",
        )

    def _ensure_directories(self) -> None:
        for path in (self.incoming, self.processing, self.failed):
            path.mkdir(parents=True, exist_ok=True)
            if os.name != "nt":
                path.chmod(0o700)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                for job_id, pdf_path, sidecar_path, metadata in self.get_completed_jobs():
                    try:
                        self.service.submit_captured_job(
                            job_id, pdf_path, sidecar_path, metadata
                        )
                    except Exception as error:
                        self.fail_processing(job_id, str(error))
                        self.service.record_capture_failure(job_id, metadata, str(error))
            except Exception:
                self._logger.exception("print_capture_scan_failed")
            self.service.expire_and_cleanup()
            self._stop_event.wait(self.poll_interval)

    def _read_metadata(self, path: Path) -> CaptureMetadata:
        if path.stat().st_size > 64 * 1024:
            raise ValueError("Metadata sidecar is too large")
        try:
            value: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("Metadata sidecar is not valid UTF-8 JSON") from error
        return CaptureMetadata.from_dict(value)

    def _validate_pdf(self, path: Path) -> None:
        size = path.stat().st_size
        maximum = self.service.settings.get().max_job_size_bytes
        if size <= 0:
            raise ValueError("PDF is empty")
        if size > maximum:
            raise ValueError(f"PDF exceeds the {maximum}-byte print-job limit")
        with path.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                raise ValueError("File does not have a valid PDF signature")

    def _move_to_processing(self, job_id: str, pdf: Path, sidecar: Path) -> tuple[Path, Path]:
        processing_pdf = self.processing / f"{job_id}.pdf"
        processing_sidecar = self.processing / f"{job_id}.json"
        if processing_pdf.exists() or processing_sidecar.exists():
            raise ValueError("Duplicate print-job ID")
        os.replace(pdf, processing_pdf)
        try:
            os.replace(sidecar, processing_sidecar)
        except Exception:
            os.replace(processing_pdf, pdf)
            raise
        return processing_pdf, processing_sidecar

    def _fail_incoming(self, job_id: str, reason: str) -> None:
        self.failed.mkdir(parents=True, exist_ok=True)
        for suffix in (".pdf", ".json"):
            source = self.incoming / f"{job_id}{suffix}"
            if source.exists():
                target = self.failed / source.name
                if target.exists():
                    target = self.failed / f"{job_id}.{uuid.uuid4().hex}{suffix}"
                shutil.move(str(source), str(target))
        (self.failed / f"{job_id}.error.json").write_text(
            json.dumps({"job_id": job_id, "error": str(reason)[:500]}, indent=2),
            encoding="utf-8",
        )
