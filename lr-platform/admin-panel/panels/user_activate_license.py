import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from resources.styles import (
    BG,
    BORDER,
    DANGER,
    MUTED,
    PRIMARY,
    SOFT_GREEN,
    SUCCESS,
    SURFACE,
    TEXT,
    WARNING,
    button,
    plain_button,
)


STATUS_LABELS = {
    "LICENSED": "Licensed",
    "TRIAL_ACTIVE": "Pending activation",
    "TRIAL_EXPIRED": "Trial expired",
    "HELD": "Blocked",
    "DEVICE_CHANGED": "Device changed",
    "NOT_FOUND": "Not activated",
}


class UserActivateLicenseTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.users = []
        self.filtered_users = []
        self._loading = False
        self._build()

    def _build(self):
        header = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        header.pack(fill=tk.X, padx=14, pady=(14, 10))

        heading = tk.Frame(header, bg=SURFACE)
        heading.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=18, pady=14)
        tk.Label(
            heading,
            text="User License Activation",
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI", 17, "bold"),
        ).pack(anchor=tk.W)
        tk.Label(
            heading,
            text=(
                "Assign an LR license to a user. License keys are never entered "
                "in the desktop client or web view."
            ),
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W, pady=(3, 0))

        self.refresh_button = plain_button(header, "Refresh", self.refresh)
        self.refresh_button.pack(side=tk.RIGHT, padx=18, pady=14)

        stats = tk.Frame(self, bg=BG)
        stats.pack(fill=tk.X, padx=14, pady=(0, 10))
        self.stat_labels = {}
        stat_specs = (
            ("total_users", "License users", PRIMARY),
            ("licensed", "Licensed", SUCCESS),
            ("pending", "Unlicensed", WARNING),
            ("blocked", "Blocked", DANGER),
        )
        for index, (key, title, color) in enumerate(stat_specs):
            card = tk.Frame(
                stats,
                bg=SURFACE,
                highlightbackground=BORDER,
                highlightthickness=1,
            )
            card.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 5, 0))
            stats.grid_columnconfigure(index, weight=1)
            tk.Label(
                card,
                text=title,
                bg=SURFACE,
                fg=MUTED,
                font=("Segoe UI", 9, "bold"),
            ).pack(anchor=tk.W, padx=14, pady=(10, 0))
            value = tk.Label(
                card,
                text="0",
                bg=SURFACE,
                fg=color,
                font=("Segoe UI", 20, "bold"),
            )
            value.pack(anchor=tk.W, padx=14, pady=(0, 9))
            self.stat_labels[key] = value

        content = tk.PanedWindow(
            self,
            orient=tk.HORIZONTAL,
            bg=BG,
            bd=0,
            sashwidth=8,
            sashrelief=tk.FLAT,
        )
        content.pack(fill=tk.BOTH, expand=True, padx=14, pady=(0, 14))

        list_card = tk.Frame(
            content,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        detail_card = tk.Frame(
            content,
            bg=SURFACE,
            width=360,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        content.add(list_card, minsize=520, stretch="always")
        content.add(detail_card, minsize=330, stretch="never")

        toolbar = tk.Frame(list_card, bg=SURFACE)
        toolbar.pack(fill=tk.X, padx=12, pady=12)
        tk.Label(
            toolbar,
            text="Users",
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI", 12, "bold"),
        ).pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_args: self._apply_filter())
        search = ttk.Entry(toolbar, textvariable=self.search_var, width=30)
        search.pack(side=tk.RIGHT)
        tk.Label(
            toolbar,
            text="Search",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(side=tk.RIGHT, padx=(0, 7))

        columns = ("username", "email", "status", "plan", "expires")
        self.tree = ttk.Treeview(
            list_card,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        headings = {
            "username": ("User", 135),
            "email": ("Email", 185),
            "status": ("Status", 125),
            "plan": ("Plan", 85),
            "expires": ("Expires", 100),
        }
        for column, (title, width) in headings.items():
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, minwidth=70, anchor=tk.W)
        self.tree.tag_configure("licensed", foreground=SUCCESS)
        self.tree.tag_configure("blocked", foreground=DANGER)
        self.tree.tag_configure("pending", foreground=WARNING)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        detail = tk.Frame(detail_card, bg=SURFACE)
        detail.pack(fill=tk.BOTH, expand=True, padx=18, pady=16)
        tk.Label(
            detail,
            text="Activate for selected user",
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor=tk.W)
        tk.Label(
            detail,
            text=(
                "Select a user, paste the LR-Key, then activate. "
                "The license becomes available on the user's next login."
            ),
            bg=SURFACE,
            fg=MUTED,
            justify=tk.LEFT,
            wraplength=310,
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W, pady=(5, 16))

        self.selected_user_label = tk.Label(
            detail,
            text="No user selected",
            bg=SOFT_GREEN,
            fg=TEXT,
            anchor=tk.W,
            justify=tk.LEFT,
            padx=12,
            pady=10,
            font=("Segoe UI", 10, "bold"),
        )
        self.selected_user_label.pack(fill=tk.X)

        self.selected_status_label = tk.Label(
            detail,
            text="Select a row to view license status.",
            bg=SURFACE,
            fg=MUTED,
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=310,
            font=("Segoe UI", 9),
        )
        self.selected_status_label.pack(fill=tk.X, pady=(8, 18))

        tk.Label(
            detail,
            text="LR License Key",
            bg=SURFACE,
            fg=TEXT,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor=tk.W)
        self.license_key_var = tk.StringVar()
        self.license_key_entry = ttk.Entry(
            detail,
            textvariable=self.license_key_var,
            show="*",
            font=("Consolas", 11),
        )
        self.license_key_entry.pack(fill=tk.X, ipady=5, pady=(5, 7))
        self.show_key_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            detail,
            text="Show license key",
            variable=self.show_key_var,
            command=self._toggle_key_visibility,
        ).pack(anchor=tk.W)

        self.activate_button = button(
            detail,
            "Activate License",
            self.activate_selected,
            SUCCESS,
        )
        self.activate_button.pack(fill=tk.X, pady=(18, 8))

        self.action_status = tk.Label(
            detail,
            text="",
            bg=SURFACE,
            fg=MUTED,
            justify=tk.LEFT,
            wraplength=310,
            font=("Segoe UI", 9),
        )
        self.action_status.pack(anchor=tk.W)

    def refresh(self):
        if self._loading or not self.app.require_login():
            return
        self._set_loading(True, "Loading user licenses...")

        def worker():
            try:
                data = self.app.client.user_licenses()
            except Exception as error:
                self.after(0, lambda: self._finish_refresh(None, error))
                return
            self.after(0, lambda: self._finish_refresh(data, None))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_refresh(self, data, error):
        self._set_loading(False)
        if error:
            self.action_status.config(text=f"Refresh failed: {error}", fg=DANGER)
            self.app.set_status(f"License refresh failed: {error}")
            return

        self.users = list((data or {}).get("users") or [])
        summary = (data or {}).get("summary") or {}
        for key, label in self.stat_labels.items():
            label.config(text=str(summary.get(key, 0)))
        self._apply_filter()
        self.app.set_status(f"Loaded license status for {len(self.users)} users")

    def _apply_filter(self):
        needle = self.search_var.get().strip().lower()
        self.filtered_users = [
            user for user in self.users
            if not needle or needle in " ".join((
                str(user.get("username") or ""),
                str(user.get("email") or ""),
                str((user.get("license") or {}).get("status") or ""),
            )).lower()
        ]

        selected_id = self._selected_user_id()
        for item in self.tree.get_children():
            self.tree.delete(item)
        for user in self.filtered_users:
            license_info = user.get("license") or {}
            state = str(license_info.get("status") or "NOT_FOUND")
            tag = "licensed" if state == "LICENSED" else (
                "blocked" if license_info.get("blocked") else "pending"
            )
            self.tree.insert(
                "",
                tk.END,
                iid=str(user.get("id")),
                values=(
                    user.get("username") or "-",
                    user.get("email") or "-",
                    STATUS_LABELS.get(state, state.replace("_", " ").title()),
                    license_info.get("plan_name") or "-",
                    self._format_date(license_info.get("expires_at")),
                ),
                tags=(tag,),
            )
        if selected_id and self.tree.exists(selected_id):
            self.tree.selection_set(selected_id)
            self.tree.focus(selected_id)

    def _on_select(self, _event=None):
        user = self._selected_user()
        if not user:
            return
        license_info = user.get("license") or {}
        state = str(license_info.get("status") or "NOT_FOUND")
        status_text = STATUS_LABELS.get(state, state.replace("_", " ").title())
        days = license_info.get("days_remaining")
        details = [f"Status: {status_text}"]
        if license_info.get("plan_name"):
            details.append(f"Plan: {license_info['plan_name']}")
        if license_info.get("expires_at"):
            details.append(f"Expires: {self._format_date(license_info['expires_at'])}")
        if days is not None:
            details.append(f"Days remaining: {days}")

        self.selected_user_label.config(
            text=f"{user.get('username') or '-'}\n{user.get('email') or 'No email'}"
        )
        self.selected_status_label.config(text="\n".join(details))
        self.action_status.config(text="", fg=MUTED)

    def activate_selected(self):
        if self._loading or not self.app.require_login():
            return
        user = self._selected_user()
        if not user:
            messagebox.showwarning("Activate License", "Select a user first.")
            return
        license_key = self.license_key_var.get().strip()
        if not license_key:
            messagebox.showwarning("Activate License", "Enter the LR license key.")
            self.license_key_entry.focus_set()
            return

        username = user.get("username") or "this user"
        if not messagebox.askyesno(
            "Activate License",
            f"Assign this license key to {username}?",
        ):
            return

        self._set_loading(True, f"Activating license for {username}...")

        def worker():
            try:
                result = self.app.client.activate_user_license(
                    user.get("id"),
                    license_key,
                )
            except Exception as error:
                self.after(0, lambda: self._finish_activation(None, error))
                return
            self.after(0, lambda: self._finish_activation(result, None))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_activation(self, result, error):
        self._set_loading(False)
        if error:
            self.action_status.config(text=f"Activation failed: {error}", fg=DANGER)
            messagebox.showerror("Activate License", f"Activation failed: {error}")
            return

        self.license_key_var.set("")
        message = (result or {}).get("message") or "License activated successfully."
        self.action_status.config(text=message, fg=SUCCESS)
        messagebox.showinfo("Activate License", message)
        self.refresh()

    def _set_loading(self, loading, message=None):
        self._loading = loading
        state = tk.DISABLED if loading else tk.NORMAL
        self.activate_button.config(state=state)
        self.refresh_button.config(state=state)
        if message:
            self.action_status.config(text=message, fg=PRIMARY)
            self.app.set_status(message)

    def _toggle_key_visibility(self):
        self.license_key_entry.config(show="" if self.show_key_var.get() else "*")

    def _selected_user_id(self):
        selection = self.tree.selection()
        return str(selection[0]) if selection else None

    def _selected_user(self):
        user_id = self._selected_user_id()
        if not user_id:
            return None
        return next(
            (user for user in self.users if str(user.get("id")) == user_id),
            None,
        )

    @staticmethod
    def _format_date(value):
        if not value:
            return "-"
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.strftime("%d %b %Y")
        except (TypeError, ValueError):
            return str(value)[:10]
