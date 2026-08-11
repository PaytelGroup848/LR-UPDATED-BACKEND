import tkinter as tk
from tkinter import messagebox, ttk

from api_client import ApiError
from resources.styles import DANGER, PRIMARY, SUCCESS, button, plain_button


class PrintingTab(ttk.Frame):
    """Administrative controls and live status for LR remote printing."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.enabled = tk.BooleanVar(value=True)
        self.max_size = tk.StringVar(value="50")
        self.timeout = tk.StringVar(value="120")
        self.retention = tk.StringVar(value="300")
        self.default_mode = tk.StringVar(value="ask")
        self.browser_fallback = tk.BooleanVar(value=True)
        self.automatic = tk.BooleanVar(value=False)
        self.allowed_modes = tk.StringVar(value="ask,default,preview,save,selected")
        self._build()

    def _build(self):
        toolbar = ttk.Frame(self, padding=(12, 10))
        toolbar.pack(fill=tk.X)
        button(toolbar, "Save Printing Settings", self.save, SUCCESS).pack(side=tk.LEFT, padx=(0, 8))
        plain_button(toolbar, "Refresh", self.refresh).pack(side=tk.LEFT, padx=(0, 8))
        button(toolbar, "Clear Expired", self.clear_expired, DANGER).pack(side=tk.LEFT)

        settings = ttk.LabelFrame(self, text="Remote printing configuration", padding=12)
        settings.pack(fill=tk.X, padx=12, pady=(0, 10))
        ttk.Checkbutton(settings, text="Enable remote printing globally", variable=self.enabled).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=4
        )
        ttk.Checkbutton(settings, text="Enable browser PDF fallback", variable=self.browser_fallback).grid(
            row=0, column=2, columnspan=2, sticky=tk.W, pady=4
        )
        ttk.Checkbutton(settings, text="Allow automatic printing", variable=self.automatic).grid(
            row=0, column=4, columnspan=2, sticky=tk.W, pady=4
        )
        fields = (
            ("Maximum PDF size (MB)", self.max_size),
            ("Job timeout (seconds)", self.timeout),
            ("Temporary retention (seconds)", self.retention),
        )
        for index, (label, variable) in enumerate(fields):
            column = index * 2
            ttk.Label(settings, text=label).grid(row=1, column=column, sticky=tk.W, pady=(10, 3))
            ttk.Entry(settings, textvariable=variable, width=16).grid(
                row=2, column=column, sticky=tk.W, padx=(0, 20)
            )
        ttk.Label(settings, text="Default mode").grid(row=3, column=0, sticky=tk.W, pady=(10, 3))
        ttk.Combobox(
            settings,
            textvariable=self.default_mode,
            values=("ask", "default", "preview", "save"),
            state="readonly",
            width=18,
        ).grid(row=4, column=0, sticky=tk.W)
        ttk.Label(settings, text="Allowed modes (comma separated)").grid(
            row=3, column=2, columnspan=2, sticky=tk.W, pady=(10, 3)
        )
        ttk.Entry(settings, textvariable=self.allowed_modes, width=44).grid(
            row=4, column=2, columnspan=2, sticky=tk.W
        )

        panes = ttk.Panedwindow(self, orient=tk.VERTICAL)
        panes.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        clients_frame = ttk.LabelFrame(panes, text="Active print-capable sessions", padding=6)
        jobs_frame = ttk.LabelFrame(panes, text="Recent and failed print jobs", padding=6)
        panes.add(clients_frame, weight=1)
        panes.add(jobs_frame, weight=2)

        self.clients_tree = ttk.Treeview(
            clients_frame,
            columns=("session", "connection", "user", "type", "seen"),
            show="headings",
            height=5,
        )
        for key, title, width in (
            ("session", "Session", 210),
            ("connection", "Connection", 210),
            ("user", "User", 170),
            ("type", "Client", 85),
            ("seen", "Last seen", 190),
        ):
            self.clients_tree.heading(key, text=title)
            self.clients_tree.column(key, width=width, anchor=tk.W)
        self.clients_tree.pack(fill=tk.BOTH, expand=True)

        self.jobs_tree = ttk.Treeview(
            jobs_frame,
            columns=("job", "session", "state", "size", "created", "error"),
            show="headings",
            height=9,
        )
        for key, title, width in (
            ("job", "Job ID", 220),
            ("session", "Session", 190),
            ("state", "State", 90),
            ("size", "Size", 90),
            ("created", "Created", 180),
            ("error", "Failure reason", 300),
        ):
            self.jobs_tree.heading(key, text=title)
            self.jobs_tree.column(key, width=width, anchor=tk.W)
            self.jobs_tree.pack(fill=tk.BOTH, expand=True)

    def refresh(self):
        if not self.app.require_login():
            return
        try:
            settings = self.app.client.printing_settings().get("settings", {})
            status = self.app.client.printing_status()
            jobs = self.app.client.printing_jobs(limit=300)
            self._set_settings(settings)
            self._replace_clients(status.get("active_clients", []))
            self._replace_jobs(jobs)
            self.app.set_status("Printing status refreshed")
        except ApiError as error:
            self.app.set_status(f"Printing refresh failed: {error}")
            messagebox.showerror("Printing", str(error))

    def save(self):
        if not self.app.require_login():
            return
        try:
            payload = {
                "enabled": self.enabled.get(),
                "max_job_size_mb": int(self.max_size.get()),
                "job_timeout_seconds": int(self.timeout.get()),
                "temp_retention_seconds": int(self.retention.get()),
                "default_mode": self.default_mode.get(),
                "browser_fallback": self.browser_fallback.get(),
                "automatic_printing": self.automatic.get(),
                "allowed_modes": [
                    value.strip().lower()
                    for value in self.allowed_modes.get().split(",")
                    if value.strip()
                ],
            }
            result = self.app.client.save_printing_settings(payload)
            self._set_settings(result.get("settings", {}))
            self.app.set_status("Printing settings saved")
            messagebox.showinfo("Printing", "Remote printing settings saved.")
        except (ApiError, ValueError) as error:
            messagebox.showerror("Printing", str(error))

    def clear_expired(self):
        if not self.app.require_login():
            return
        try:
            result = self.app.client.clear_expired_print_jobs()
            self.app.set_status(f"Cleared {result.get('cleared', 0)} expired print jobs")
            self.refresh()
        except ApiError as error:
            messagebox.showerror("Printing", str(error))

    def _set_settings(self, value):
        self.enabled.set(bool(value.get("enabled", True)))
        self.max_size.set(str(value.get("max_job_size_mb", 50)))
        self.timeout.set(str(value.get("job_timeout_seconds", 120)))
        self.retention.set(str(value.get("temp_retention_seconds", 300)))
        self.default_mode.set(str(value.get("default_mode", "ask")))
        self.browser_fallback.set(bool(value.get("browser_fallback", True)))
        self.automatic.set(bool(value.get("automatic_printing", False)))
        self.allowed_modes.set(",".join(value.get("allowed_modes", [])))

    def _replace_clients(self, values):
        self.clients_tree.delete(*self.clients_tree.get_children())
        for item in values:
            self.clients_tree.insert("", tk.END, values=(
                item.get("session_id", ""),
                item.get("connection_id", ""),
                item.get("user_id", ""),
                item.get("client_type", ""),
                item.get("last_seen_at", ""),
            ))

    def _replace_jobs(self, values):
        self.jobs_tree.delete(*self.jobs_tree.get_children())
        for item in values:
            self.jobs_tree.insert("", tk.END, values=(
                item.get("job_id", ""),
                item.get("session_id", ""),
                item.get("state", ""),
                item.get("size", 0),
                item.get("created_at", ""),
                item.get("error", "") or "",
            ))
