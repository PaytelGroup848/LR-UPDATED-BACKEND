import sys
import threading
from pathlib import Path
from tkinter import messagebox
from typing import Any, Callable, TYPE_CHECKING

import customtkinter as ctk
from PIL import Image

from config import DEFAULT_COMPANY_CODE, DEFAULT_SERVER_URL
from session.api_client import LRApi


VIEW_MODE_OPTIONS = ("Desktop View", "Remote App View")
VIEW_MODE_VALUES = {
    "Desktop View": "rdp_desktop",
    "Remote App View": "rdp_remote_app",
}
VIEW_MODE_HELP = {
    "rdp_desktop": "Open your complete assigned Windows desktop.",
    "rdp_remote_app": "Open only your assigned published applications.",
}


class LoginWindowMixin:
    if TYPE_CHECKING:
        root: Any
        api: LRApi
        status: Any
        logo_image: Any
        company_entry: Any
        username_entry: Any
        password_entry: Any
        view_mode_var: Any
        view_selector: Any
        view_mode_help: Any

        def clear(self) -> None: ...
        def run_async(self, target: Callable[[], Any]) -> None: ...
        def show_apps(self, apps: list[dict[str, Any]]) -> None: ...
        def open_desktop_login_response(self, result: dict[str, Any]) -> None: ...

    def _resource_path(self, filename):
        base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
        return base_path / "resources" / filename

    def _load_logo_image(self, size=(220, 60)):
        logo_path = self._resource_path("lr-remote-logo.png")
        if not logo_path.exists():
            return None
        image = Image.open(logo_path)
        return ctk.CTkImage(light_image=image, dark_image=image, size=size)

    def show_login(self):
        self.clear()
        width, height = 760, 640
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 2)
        self.root.title("LR Remote Access")
        self.root.resizable(True, True)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(700, 600)
        self.root.configure(fg_color="#eaf2ff")
        self.server_entry = None
        self.two_factor_entry = None
        self.remember_me = None

        surface = ctk.CTkFrame(
            self.root,
            width=660,
            height=570,
            corner_radius=28,
            fg_color="#ffffff",
            border_width=1,
            border_color="#cbdcf5",
        )
        surface.place(relx=0.5, rely=0.5, anchor="center")
        surface.pack_propagate(False)

        brand = ctk.CTkFrame(surface, width=190, fg_color="#0b376d", corner_radius=24)
        brand.pack(side="left", fill="y", padx=(12, 0), pady=12)
        brand.pack_propagate(False)

        self.logo_image = self._load_logo_image(size=(150, 42))
        if self.logo_image:
            ctk.CTkLabel(brand, image=self.logo_image, text="").pack(pady=(64, 26))
        else:
            ctk.CTkLabel(
                brand, text="LR", text_color="#ffffff",
                font=("Segoe UI", 46, "bold"),
            ).pack(pady=(64, 26))

        ctk.CTkLabel(
            brand,
            text="Native Windows RDP",
            text_color="#ffffff",
            font=("Segoe UI", 16, "bold"),
        ).pack()
        ctk.CTkLabel(
            brand,
            text="Full desktop or floating\nRemoteApp access through\nyour assigned  server.",
            text_color="#cfe3ff",
            justify="center",
            font=("Segoe UI", 11),
        ).pack(padx=18, pady=(12, 0))

        form = ctk.CTkFrame(surface, fg_color="transparent")
        form.pack(side="right", fill="both", expand=True, padx=34, pady=30)

        # Keep the primary login action visible even when Windows display or
        # text scaling makes the fields taller than the available form area.
        # Only the fields scroll; the action area stays pinned at the bottom.
        form.grid_columnconfigure(0, weight=1)
        form.grid_rowconfigure(0, weight=1)
        fields = ctk.CTkScrollableFrame(
            form,
            fg_color="transparent",
            corner_radius=0,
            scrollbar_button_color="#cbdcf5",
            scrollbar_button_hover_color="#9fb8d8",
        )
        fields.grid(row=0, column=0, sticky="nsew")
        actions = ctk.CTkFrame(form, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", pady=(10, 0))

        ctk.CTkLabel(
            fields, text="Connect to remote computer",
            text_color="#0f172a", font=("Segoe UI", 22, "bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            fields, text="Enter your LR/Windows account credentials.",
            text_color="#64748b", font=("Segoe UI", 11),
        ).pack(anchor="w", pady=(3, 14))

        ctk.CTkLabel(
            fields, text="Company code", text_color="#334155",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        self.company_entry = ctk.CTkEntry(
            fields, placeholder_text="Company code", width=330, height=38,
            corner_radius=9, border_color="#b8c8dc",
        )
        if DEFAULT_COMPANY_CODE:
            self.company_entry.insert(0, DEFAULT_COMPANY_CODE)
        self.company_entry.pack(fill="x")

        ctk.CTkLabel(
            fields, text="Username", text_color="#334155",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(10, 4))
        self.username_entry = ctk.CTkEntry(
            fields, placeholder_text="Username", width=330, height=42,
            corner_radius=9, border_color="#b8c8dc",
        )
        self.username_entry.pack(fill="x")

        ctk.CTkLabel(
            fields, text="Password", text_color="#334155",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(12, 4))
        self.password_entry = ctk.CTkEntry(
            fields, placeholder_text="Password", show="*", width=330, height=42,
            corner_radius=9, border_color="#b8c8dc",
        )
        self.password_entry.pack(fill="x")
        self.password_entry.bind("<Return>", lambda _event: self.login())

        # Keep both native connection choices pinned with the Login button.
        # They must never disappear below the scrollable credential fields.
        ctk.CTkLabel(
            actions, text="Connection view", text_color="#334155",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 5))
        self.view_mode_var = ctk.StringVar(value="rdp_desktop")
        self.view_selector = ctk.CTkSegmentedButton(
            actions,
            values=list(VIEW_MODE_OPTIONS),
            command=self._set_view_mode,
            width=330,
            height=42,
            selected_color="#08a85a",
            selected_hover_color="#07894b",
        )
        self.view_selector.set("Desktop View")
        self.view_selector.pack(fill="x")

        self.view_mode_help = ctk.CTkLabel(
            actions,
            text=VIEW_MODE_HELP["rdp_desktop"],
            text_color="#64748b", font=("Segoe UI", 9),
        )
        self.view_mode_help.pack(anchor="w", pady=(6, 10))

        ctk.CTkButton(
            actions,
            text="Login",
            command=self.login,
            height=44,
            corner_radius=10,
            font=("Segoe UI", 14, "bold"),
            fg_color="#08a85a",
            hover_color="#07894b",
        ).pack(fill="x")
        ctk.CTkButton(
            actions,
            text="Remote Printing Settings",
            command=self.show_print_settings,
            height=32,
            corner_radius=9,
            fg_color="#eff8f4",
            hover_color="#dcefe6",
            text_color="#087846",
        ).pack(fill="x", pady=(8, 0))

        self.status = ctk.CTkLabel(
            actions, text="Ready", text_color="#64748b",
            font=("Segoe UI", 10),
        )
        self.status.pack(anchor="w", pady=(9, 0))
        self.root.after(100, self.username_entry.focus_force)

    def login(self):
        company = self.company_entry.get().strip() if self.company_entry else ""
        username = self.username_entry.get().strip()
        cached_password = None
        if username == getattr(self, "_rdp_session_username", None):
            cached_password = getattr(self, "_rdp_session_password", None)
        password = self.password_entry.get() or cached_password
        if not company or not username or not password:
            messagebox.showerror(
                "LR Remote Access",
                "Company code, username and password are required.",
            )
            return

        self.status.configure(text="Authenticating and checking license...", text_color="#2563eb")
        server_url = self._server_url()
        self.api = LRApi(server_url)
        self.run_async(lambda: self._login(username, password, company))

    def _set_view_mode(self, value):
        selected_mode = VIEW_MODE_VALUES.get(value, "rdp_desktop")
        self.view_mode_var.set(selected_mode)
        help_label = getattr(self, "view_mode_help", None)
        if help_label and help_label.winfo_exists():
            help_label.configure(text=VIEW_MODE_HELP[selected_mode])

    def _login(self, username, password, company=None):
        selected_mode = self.view_mode_var.get() if self.view_mode_var else "rdp_desktop"
        connection_type = "remoteapp" if selected_mode == "rdp_remote_app" else "desktop"
        payload = {
            "username": username,
            "password": password,
            "connection_type": connection_type,
        }
        if str(company or "").strip():
            payload["company_code"] = str(company).strip()

        try:
            login_result = self.api.post_json("/login", payload)
            self._rdp_session_password = password
            self._rdp_session_username = username
            self.root.after(0, self._clear_visible_password)
            self.current_user = login_result.get("user") or {"username": username}
            license_info = self.api.get_json("/license/me")
            if license_info.get("blocked"):
                self.root.after(0, lambda: self._show_license_blocked(license_info))
                return

            if selected_mode == "rdp_desktop":
                desktop_result = self.api.post_json("/api/lr/desktop", {})
                self.root.after(
                    0,
                    lambda result=desktop_result: self.open_desktop_login_response(result),
                )
                return

            resources_url = login_result.get("resources_url") or "/api/lr/my-resources"
            resources = self.api.get_json(resources_url)
            apps = list(resources.get("applications", [])) + list(resources.get("folders", []))
            self.root.after(0, lambda: self.show_apps(apps))

        except RuntimeError as error:
            message = str(error)
            server_url = getattr(self.api, "base_url", None) or self._server_url()
            if "Connection refused" in message or "actively refused" in message:
                message = (
                    f"{message}\n\nCheck that the LR gateway service is running at "
                    f"{server_url}."
                )
            elif "Not Found" in message or "404" in message:
                message = (
                    f"{message}\n\nThe configured LR gateway does not expose the required RDP API."
                )
            raise RuntimeError(message)

    def _show_license_blocked(self, license_info):
        message = (license_info or {}).get("message") or (
            "Your LR Remote Access license is not active. "
            "Please contact your administrator."
        )
        self.status.configure(text="License activation required", text_color="#dc2626")
        messagebox.showwarning("LR Remote Access", message)

    def _clear_visible_password(self):
        entry = getattr(self, "password_entry", None)
        if entry and entry.winfo_exists():
            entry.delete(0, "end")

    def logout(self):
        api = self.api
        print_agents = getattr(self, "print_agents", None)
        if print_agents:
            print_agents.stop_all()
        self._clear_rdp_credentials()
        self.current_user = None
        self.api = None
        self.show_login()
        if api:
            threading.Thread(target=self._logout_backend, args=(api,), daemon=True).start()

    @staticmethod
    def _logout_backend(api):
        try:
            api.post_json("/logout", {})
        except Exception:
            pass
