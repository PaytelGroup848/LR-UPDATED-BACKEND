from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from printing.providers import get_default_printer, list_local_printers
from printing.settings import ClientPrintSettings, ClientPrintSettingsStore


ACTION_LABELS = {
    "Ask every time": "ask",
    "Print to default printer": "default",
    "Preview PDF": "preview",
    "Save PDF": "save",
}


class PrintingUiMixin:
    def show_print_settings(self) -> None:
        PrintSettingsDialog(self.root, self.print_settings_store)

    def show_print_job(self, agent, metadata: dict[str, Any], pdf_path: str) -> None:
        PrintJobDialog(self.root, agent, metadata, pdf_path)

    def update_printing_status(self, text: str) -> None:
        status = getattr(self, "status", None)
        try:
            if status and status.winfo_exists():
                status.configure(text=text)
        except Exception:
            pass


class PrintSettingsDialog(ctk.CTkToplevel):
    def __init__(self, parent, store: ClientPrintSettingsStore) -> None:
        super().__init__(parent)
        self.store = store
        settings = store.load()
        self.title("Remote Printing Settings")
        self.geometry("560x520")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.enabled = ctk.BooleanVar(value=settings.enabled)
        self.default_action = ctk.StringVar(value=next(
            label for label, value in ACTION_LABELS.items() if value == settings.default_action
        ))
        self.preferred_printer = ctk.StringVar(value=settings.preferred_printer)
        self.notification = ctk.BooleanVar(value=settings.show_notification)
        self.auto_cleanup = ctk.BooleanVar(value=settings.auto_remove_temp_files)
        self.timeout = ctk.StringVar(value=str(settings.job_timeout_seconds))
        self.retention = ctk.StringVar(value=str(settings.temp_retention_seconds))
        printers = list_local_printers()
        if settings.preferred_printer and settings.preferred_printer not in printers:
            printers.insert(0, settings.preferred_printer)
        self.printers = printers or [""]

        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=28, pady=24)
        ctk.CTkLabel(
            frame, text="Remote Printing", font=("Segoe UI", 22, "bold")
        ).pack(anchor="w", pady=(0, 12))
        ctk.CTkSwitch(
            frame, text="Enable remote printing", variable=self.enabled
        ).pack(anchor="w", pady=8)
        self._label(frame, "Default action")
        ctk.CTkOptionMenu(
            frame, values=list(ACTION_LABELS), variable=self.default_action, width=310
        ).pack(anchor="w")
        self._label(frame, "Preferred local printer")
        ctk.CTkOptionMenu(
            frame, values=self.printers, variable=self.preferred_printer, width=460
        ).pack(anchor="w")
        ctk.CTkSwitch(
            frame, text="Show notification when a print job arrives", variable=self.notification
        ).pack(anchor="w", pady=(16, 8))
        ctk.CTkSwitch(
            frame, text="Automatically remove temporary PDFs", variable=self.auto_cleanup
        ).pack(anchor="w", pady=8)

        timings = ctk.CTkFrame(frame, fg_color="transparent")
        timings.pack(fill="x", pady=(12, 0))
        left = ctk.CTkFrame(timings, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        right = ctk.CTkFrame(timings, fg_color="transparent")
        right.pack(side="left", fill="x", expand=True, padx=(12, 0))
        self._label(left, "Transfer timeout (seconds)")
        ctk.CTkEntry(left, textvariable=self.timeout, width=210).pack(anchor="w")
        self._label(right, "Local retention (seconds)")
        ctk.CTkEntry(right, textvariable=self.retention, width=210).pack(anchor="w")

        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.pack(fill="x", side="bottom", pady=(20, 0))
        ctk.CTkButton(actions, text="Cancel", fg_color="#64748b", command=self.destroy).pack(
            side="right"
        )
        ctk.CTkButton(actions, text="Save", fg_color="#08a85a", command=self._save).pack(
            side="right", padx=(0, 10)
        )

    @staticmethod
    def _label(parent, text: str) -> None:
        ctk.CTkLabel(parent, text=text, font=("Segoe UI", 11, "bold")).pack(
            anchor="w", pady=(12, 4)
        )

    def _save(self) -> None:
        try:
            settings = ClientPrintSettings.from_dict({
                "enabled": self.enabled.get(),
                "default_action": ACTION_LABELS[self.default_action.get()],
                "preferred_printer": self.preferred_printer.get(),
                "show_notification": self.notification.get(),
                "auto_remove_temp_files": self.auto_cleanup.get(),
                "job_timeout_seconds": int(self.timeout.get()),
                "temp_retention_seconds": int(self.retention.get()),
            })
            self.store.save(settings)
            messagebox.showinfo("Remote Printing", "Printing settings saved.", parent=self)
            self.destroy()
        except Exception as error:
            messagebox.showerror("Remote Printing", str(error), parent=self)


class PrintJobDialog(ctk.CTkToplevel):
    def __init__(self, parent, agent, metadata: dict[str, Any], pdf_path: str) -> None:
        super().__init__(parent)
        self.agent = agent
        self.metadata = metadata
        self.pdf_path = pdf_path
        self.title("LR Remote Print Job")
        self.geometry("640x500")
        self.minsize(600, 470)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.attributes("-topmost", True)

        printers = agent.list_printers()
        default = get_default_printer()
        preferred = agent.settings_store.load().preferred_printer
        initial = preferred if preferred in printers else default if default in printers else printers[0] if printers else "No printers installed"
        self.printers = printers
        self.printer = ctk.StringVar(value=initial)
        self.copies = ctk.StringVar(value=str(metadata.get("copies") or 1))

        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=26, pady=22)
        ctk.CTkLabel(
            frame, text="Remote print job received", font=("Segoe UI", 22, "bold")
        ).pack(anchor="w")
        ctk.CTkLabel(
            frame,
            text=str(metadata.get("document_name") or "Document"),
            font=("Segoe UI", 16, "bold"),
            text_color="#0f766e",
        ).pack(anchor="w", pady=(12, 2))
        size_mb = int(metadata.get("size") or 0) / (1024 * 1024)
        ctk.CTkLabel(
            frame, text=f"PDF document • {size_mb:.2f} MB", text_color="#64748b"
        ).pack(anchor="w", pady=(0, 16))

        form = ctk.CTkFrame(frame, corner_radius=14)
        form.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(form, text="Local printer", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 4)
        )
        self.printer_menu = ctk.CTkOptionMenu(
            form, values=printers or ["No printers installed"], variable=self.printer, width=410
        )
        self.printer_menu.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 14))
        ctk.CTkLabel(form, text="Copies", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=1, sticky="w", padx=16, pady=(14, 4)
        )
        ctk.CTkEntry(form, textvariable=self.copies, width=90).grid(
            row=1, column=1, sticky="w", padx=16, pady=(0, 14)
        )

        self.status = ctk.CTkLabel(frame, text="Choose an action", text_color="#64748b")
        self.status.pack(anchor="w", pady=(0, 10))
        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.pack(fill="x")
        self.buttons = [
            ctk.CTkButton(actions, text="Print", command=self._print_selected, fg_color="#08a85a"),
            ctk.CTkButton(actions, text="Print to Default", command=self._print_default),
            ctk.CTkButton(actions, text="Preview", command=self._preview, fg_color="#2563eb"),
            ctk.CTkButton(actions, text="Save PDF", command=self._save, fg_color="#0f766e"),
            ctk.CTkButton(actions, text="Cancel", command=self._cancel, fg_color="#64748b"),
        ]
        for index, button in enumerate(self.buttons):
            button.grid(row=index // 3, column=index % 3, padx=5, pady=5, sticky="ew")
            actions.grid_columnconfigure(index % 3, weight=1)

    def _validated_copies(self) -> int:
        try:
            copies = int(self.copies.get())
        except ValueError as error:
            raise ValueError("Copies must be a number") from error
        if not 1 <= copies <= 99:
            raise ValueError("Copies must be between 1 and 99")
        return copies

    def _print_selected(self) -> None:
        if not self.printers:
            messagebox.showerror("Remote Printing", "No local printers are installed.", parent=self)
            return
        try:
            copies = self._validated_copies()
        except ValueError as error:
            messagebox.showerror("Remote Printing", str(error), parent=self)
            return
        self._begin("selected", printer_name=self.printer.get(), copies=copies)

    def _print_default(self) -> None:
        try:
            self._begin("default", copies=self._validated_copies())
        except ValueError as error:
            messagebox.showerror("Remote Printing", str(error), parent=self)

    def _preview(self) -> None:
        self._begin("preview")

    def _save(self) -> None:
        suggested = str(self.metadata.get("document_name") or "document") + ".pdf"
        destination = filedialog.asksaveasfilename(
            parent=self,
            title="Save remote print PDF",
            initialfile=suggested,
            defaultextension=".pdf",
            filetypes=[("PDF document", "*.pdf")],
        )
        if destination:
            self._begin("save", destination=destination)

    def _cancel(self) -> None:
        self._begin("cancel")

    def _begin(self, action: str, **kwargs) -> None:
        for button in self.buttons:
            button.configure(state="disabled")
        self.status.configure(text="Working...", text_color="#2563eb")
        self.agent.perform_action(
            self.metadata,
            self.pdf_path,
            action,
            completion=self._completed,
            **kwargs,
        )

    def _completed(self, success: bool, message: str) -> None:
        if not self.winfo_exists():
            return
        if success:
            self.status.configure(text=message, text_color="#16a34a")
            self.after(700, self.destroy)
        else:
            self.status.configure(text=message, text_color="#dc2626")
            for button in self.buttons:
                button.configure(state="normal")
                
