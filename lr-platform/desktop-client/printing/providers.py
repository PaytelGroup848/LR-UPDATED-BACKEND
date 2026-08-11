from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path
from typing import Optional


class PrinterUnavailableError(RuntimeError):
    pass


def list_local_printers() -> list[str]:
    """List Windows local and connected printers without crashing unsupported clients."""

    if platform.system() != "Windows":
        return []
    try:
        import win32print

        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        return sorted({str(printer[2]) for printer in win32print.EnumPrinters(flags) if printer[2]})
    except Exception:
        return []


def get_default_printer() -> Optional[str]:
    if platform.system() != "Windows":
        return None
    try:
        import win32print

        value = win32print.GetDefaultPrinter()
        return str(value) if value else None
    except Exception:
        return None


def validate_printer(printer_name: str) -> None:
    name = str(printer_name or "").strip()
    if not name or len(name) > 256 or any(char in name for char in "\r\n\0"):
        raise PrinterUnavailableError("A valid local printer is required")
    if name not in list_local_printers():
        raise PrinterUnavailableError("The selected printer is unavailable")
    try:
        import win32print

        handle = win32print.OpenPrinter(name)
        try:
            info = win32print.GetPrinter(handle, 2)
            status = int(info.get("Status") or 0)
            offline = int(getattr(win32print, "PRINTER_STATUS_OFFLINE", 0x80))
            if status & offline:
                raise PrinterUnavailableError("The selected printer is offline")
        finally:
            win32print.ClosePrinter(handle)
    except PrinterUnavailableError:
        raise
    except Exception as error:
        raise PrinterUnavailableError(f"Printer access failed: {error}") from error


class PdfPrintProvider:
    def print_pdf(self, pdf_path: str, printer_name: str, copies: int = 1) -> None:
        raise NotImplementedError


class WindowsAssociatedPdfPrintProvider(PdfPrintProvider):
    """Use the registered Windows PDF handler through ShellExecute's printto verb.

    This is intentionally isolated so a bundled renderer can replace it later without
    changing transport or UI code. Printer names are passed to the Windows API and are
    never interpolated into a command line or shell command.
    """

    def print_pdf(self, pdf_path: str, printer_name: str, copies: int = 1) -> None:
        if platform.system() != "Windows":
            raise PrinterUnavailableError("Native PDF printing is supported only on Windows")
        path = Path(pdf_path).resolve()
        if not path.is_file() or path.suffix.lower() != ".pdf":
            raise ValueError("PDF file is unavailable")
        validate_printer(printer_name)
        try:
            import win32api

            for _ in range(min(max(int(copies), 1), 99)):
                result = win32api.ShellExecute(0, "printto", str(path), printer_name, None, 0)
                if int(result) <= 32:
                    raise RuntimeError(f"Windows PDF print handler returned error {result}")
        except Exception as error:
            raise RuntimeError(
                "Windows could not print the PDF. Install a PDF application that supports "
                "the Windows print-to verb, or use Preview/Save PDF."
            ) from error


def preview_pdf(pdf_path: str) -> None:
    path = Path(pdf_path).resolve()
    if not path.is_file():
        raise FileNotFoundError("Print preview file is unavailable")
    if platform.system() != "Windows":
        raise RuntimeError("PDF preview is currently supported only on Windows")
    os.startfile(str(path))


def save_pdf(pdf_path: str, destination: str) -> None:
    source = Path(pdf_path).resolve()
    target = Path(destination).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError("Print PDF is unavailable")
    if target.suffix.lower() != ".pdf":
        target = target.with_suffix(".pdf")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
