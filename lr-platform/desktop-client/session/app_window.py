import os
import re
import tempfile
import threading
import time
from tkinter import filedialog

import customtkinter as ctk

from session.credential_store import get_client_credential_store
from session.windows_credentials import prepare_rdp_for_single_sign_on

_CLIENT_LAUNCH_LOCK = threading.Lock()
_LAST_CLIENT_LAUNCH_TIME = 0.0


class AppWindowMixin:
    FLOATING_PANEL_WIDTH = 320
    FLOATING_PANEL_TOP = 48
    FLOATING_PANEL_MARGIN = 18
    FLOATING_PANEL_CHROME_HEIGHT = 236
    FLOATING_APP_ROW_HEIGHT = 62
    FLOATING_APP_LIST_MAX_HEIGHT = 260

    def open_desktop_login_response(self, result):
        rdp_file_url = result.get("rdp_file_url")
        if not rdp_file_url:
            raise RuntimeError(
                result.get("error") or "Desktop RDP file URL was not returned by the server."
            )

        desktop = {
            "id": result.get("server_id"),
            "name": result.get("server_name") or "LR Desktop",
        }
        path = self._download_rdp_file(rdp_file_url, desktop)
        session_id = result.get("session_id")
        print_agents = getattr(self, "print_agents", None)
        if session_id and print_agents:
            print_agents.start_session(self.api, session_id)
        os.startfile(path)
        self.root.after(
            0,
            lambda: self.status.configure(
                text="Full desktop opened in Windows Remote Desktop.",
                text_color="#22c55e",
            ),
        )

    def show_apps(self, apps):
        self.clear()
        self._current_apps = list(apps or [])
        username = (getattr(self, "current_user", None) or {}).get("username") or "User"
        panel_height, app_list_height, geometry = self._floating_panel_layout(
            len(self._current_apps),
            self.root.winfo_screenwidth(),
            self.root.winfo_screenheight(),
        )
        self.root.title(f"{username} Remote App")
        self.root.resizable(False, False)
        self.root.minsize(self.FLOATING_PANEL_WIDTH, panel_height)
        self.root.geometry(geometry)
        self.root.configure(fg_color="#e9f2ef")
        self.root.attributes("-topmost", True)
        self.root.lift()

        shell = ctk.CTkFrame(
            self.root,
            corner_radius=12,
            fg_color="#ffffff",
            border_width=1,
            border_color="#b8cdc5",
        )
        shell.pack(fill="both", expand=True, padx=7, pady=7)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(shell, height=88, corner_radius=10, fg_color="#f7fbfa")
        header.grid(row=0, column=0, sticky="ew", padx=7, pady=(7, 5))
        header.pack_propagate(False)
        ctk.CTkLabel(
            header,
            text=f"{username} Remote App",
            text_color="#1f3b33",
            font=("Segoe UI", 11, "bold"),
        ).place(x=10, y=7)
        logo = self._load_logo_image(size=(132, 38))
        if logo:
            self.dashboard_logo_image = logo
            ctk.CTkLabel(header, image=logo, text="").place(x=10, y=35)
        else:
            ctk.CTkLabel(
                header,
                text="LR  REMOTE ACCESS",
                text_color="#08a85a",
                font=("Segoe UI", 17, "bold"),
            ).place(x=10, y=39)
        ctk.CTkButton(
            header,
            text="↻",
            width=34,
            height=34,
            corner_radius=7,
            fg_color="#ffffff",
            hover_color="#dff2e9",
            text_color="#087846",
            border_width=1,
            border_color="#b8d8ca",
            font=("Segoe UI Symbol", 18, "bold"),
            command=self.reload_apps,
        ).place(relx=1.0, x=-10, y=44, anchor="e")

        self.app_frame = ctk.CTkScrollableFrame(
            shell,
            height=app_list_height,
            corner_radius=7,
            fg_color="#f4f8f7",
            scrollbar_button_color="#8ca9a0",
            scrollbar_button_hover_color="#668c80",
        )
        self.app_frame.grid(row=1, column=0, sticky="nsew", padx=7, pady=4)

        if not apps:
            ctk.CTkLabel(
                self.app_frame,
                text="No applications assigned",
                height=72,
                text_color="#64748b",
                font=("Segoe UI", 12, "bold"),
            ).pack(fill="x", padx=5, pady=8)
        else:
            for index, app in enumerate(apps):
                self._application_row(app, index)

        tools = ctk.CTkFrame(shell, height=35, corner_radius=6, fg_color="transparent")
        tools.grid(row=2, column=0, sticky="ew", padx=7, pady=(2, 3))
        tools.pack_propagate(False)
        for text, command in (
            ("Upload", self.upload_file),
            ("Clipboard", lambda: self._open_panel_tool(self.show_clipboard)),
            ("Ticket", lambda: self._open_panel_tool(self.show_ticket)),
            ("Printer", self.show_print_settings),
        ):
            ctk.CTkButton(
                tools,
                text=text,
                command=command,
                width=68,
                height=29,
                corner_radius=6,
                fg_color="#e8f3ef",
                hover_color="#d1e9df",
                text_color="#176246",
                font=("Segoe UI", 9, "bold"),
            ).pack(side="left", expand=True, padx=2, pady=3)

        self.status = ctk.CTkLabel(
            shell,
            text="Ready",
            height=20,
            text_color="#64748b",
            font=("Segoe UI", 9),
        )
        self.status.grid(row=3, column=0, sticky="ew", padx=10)

        ctk.CTkButton(
            shell,
            text="⏻  Logoff",
            height=39,
            corner_radius=7,
            fg_color="#b4232d",
            hover_color="#8f1922",
            text_color="#ffffff",
            font=("Segoe UI Symbol", 12, "bold"),
            command=self.logout,
        ).grid(row=4, column=0, sticky="ew", padx=7, pady=(2, 7))

    @classmethod
    def _floating_panel_layout(cls, item_count, screen_width, screen_height):
        visible_rows = max(1, min(int(item_count or 0), 4))
        app_list_height = max(84, visible_rows * cls.FLOATING_APP_ROW_HEIGHT)
        app_list_height = min(app_list_height, cls.FLOATING_APP_LIST_MAX_HEIGHT)
        panel_height = cls.FLOATING_PANEL_CHROME_HEIGHT + app_list_height
        panel_height = min(panel_height, max(320, int(screen_height) - 80))
        app_list_height = max(84, panel_height - cls.FLOATING_PANEL_CHROME_HEIGHT)
        x = max(0, int(screen_width) - cls.FLOATING_PANEL_WIDTH - cls.FLOATING_PANEL_MARGIN)
        y = min(cls.FLOATING_PANEL_TOP, max(0, int(screen_height) - panel_height))
        geometry = f"{cls.FLOATING_PANEL_WIDTH}x{panel_height}+{x}+{y}"
        return panel_height, app_list_height, geometry

    def _application_row(self, app, index):
        row = ctk.CTkFrame(
            self.app_frame,
            height=56,
            corner_radius=5,
            fg_color="#ffffff",
            border_width=1,
            border_color="#c7d8d2",
        )
        row.pack(fill="x", padx=3, pady=(3 if index == 0 else 2, 2))
        row.pack_propagate(False)

        icon_text, icon_color = self._app_icon(app)
        ctk.CTkLabel(
            row,
            text=icon_text,
            width=38,
            height=38,
            corner_radius=6,
            fg_color=icon_color,
            text_color="#ffffff",
            font=("Segoe UI Symbol", 17, "bold"),
        ).place(x=7, rely=0.5, anchor="w")

        name = app.get("name") or "Application"
        item_type = str(app.get("type") or app.get("item_type") or "").lower()
        description = (
            "Desktop folder"
            if item_type == "folder"
            else app.get("description") or app.get("server_name") or "Remote application"
        )
        ctk.CTkLabel(
            row,
            text=str(name)[:24],
            text_color="#17352b",
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        ).place(x=54, y=9)
        ctk.CTkLabel(
            row,
            text=str(description)[:27],
            text_color="#64748b",
            font=("Segoe UI", 9),
            anchor="w",
        ).place(x=54, y=30)
        ctk.CTkButton(
            row,
            text="Open",
            width=48,
            height=30,
            corner_radius=5,
            fg_color="#08a85a",
            hover_color="#07894b",
            text_color="#ffffff",
            font=("Segoe UI", 9, "bold"),
            command=lambda item=app: self.open_application(item),
        ).place(relx=1.0, x=-7, rely=0.5, anchor="e")

    def _open_panel_tool(self, command):
        self.root.resizable(True, True)
        self.root.minsize(560, 440)
        width, height = 640, 500
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        command()

    def open_application(self, app):
        self.launch_app(app)

    @staticmethod
    def _app_icon(app):
        value = str(app.get("icon") or "").strip()
        name = str(app.get("name") or "").lower()
        item_type = str(app.get("type") or app.get("item_type") or "").lower()
        if item_type == "folder":
            return "▰", "#e6a817"
        choices = (
            (("airtable",), "A", "#f59e0b"),
            (("tally", "calculator"), "∑", "#2563eb"),
            (("code", "visual studio", "vscode"), "</>", "#0284c7"),
            (("excel", "sheet"), "X", "#16a34a"),
            (("word",), "W", "#2563eb"),
            (("chrome", "browser"), "◎", "#ea4335"),
        )
        searchable = f"{name} {value.lower()}"
        for keywords, glyph, color in choices:
            if any(keyword in searchable for keyword in keywords):
                return glyph, color
        initial = (app.get("name") or "A").strip()[:1].upper()
        return initial or "A", "#08a85a"

    def launch_app(self, app):
        self.status.configure(text=f"Starting {app.get('name', 'application')}...")
        self.run_async(lambda: self._launch_app(app))

    def _launch_app(self, app):
        global _LAST_CLIENT_LAUNCH_TIME
        with _CLIENT_LAUNCH_LOCK:
            now = time.time()
            elapsed = now - _LAST_CLIENT_LAUNCH_TIME
            if elapsed < 0.5:
                time.sleep(0.5 - elapsed)
            _LAST_CLIENT_LAUNCH_TIME = time.time()

            # Handshake token sequencing: 250–300ms incremental delay per user session
            time.sleep(0.28)

            result = self.api.post_json(
                "/api/lr/launch",
                {"resource_id": app["id"], "type": app.get("type") or "application"},
            )
        rdp_file_url = result.get('rdp_file_url')

        if rdp_file_url:
            path = self._download_rdp_file(rdp_file_url, app)
            session_id = result.get("session_id")
            print_agents = getattr(self, "print_agents", None)
            if session_id and print_agents:
                print_agents.start_session(self.api, session_id)
            os.startfile(path)
            self.root.after(0, lambda: self.status.configure(text='Floating RemoteApp opened.'))
            return

        raise RuntimeError(
            result.get('error')
            or result.get('warning')
            or result.get('message')
            or 'RemoteApp RDP file URL was not returned by the server.'
        )

    def _get_rdp_password(self):
        if getattr(self, "_rdp_session_password", None):
            return self._rdp_session_password
        stored = get_client_credential_store().load()
        password = stored.get("password")
        if password:
            self._rdp_session_password = password
            return password
        return None

    def _download_rdp_file(self, url, app):
        content, headers = self.api.get_bytes(url)
        content = prepare_rdp_for_single_sign_on(
            content,
            self._get_rdp_password(),
            self._rdp_credential_cache,
        )
        filename = self._rdp_filename(headers, app)
        path = os.path.join(tempfile.gettempdir(), filename)

        with open(path, 'wb') as handle:
            handle.write(content)

        return path

    def _rdp_filename(self, headers, app):
        disposition = headers.get('Content-Disposition', '') if headers else ''
        match = re.search(r'filename="?([^";]+)"?', disposition)
        if match:
            return self._safe_filename(match.group(1))

        app_name = app.get('name') or 'lr-remote'
        return self._safe_filename(f'{app_name}.rdp')

    def _safe_filename(self, filename):
        filename = re.sub(r'[^A-Za-z0-9._-]+', '_', filename).strip('._')
        if not filename.lower().endswith('.rdp'):
            filename = f'{filename}.rdp'
        return filename or 'lr-remote.rdp'

    def upload_file(self):
        file_path = filedialog.askopenfilename()

        if not file_path:
            return

        self.status.configure(text='Uploading file...')
        self.run_async(lambda: self._upload_file(file_path))

    def _upload_file(self, file_path):
        self.api.post_file('/api/transfers', file_path)
        self.root.after(0, lambda: self.status.configure(text='File uploaded.'))

    def reload_apps(self):
        self.run_async(self._reload_apps)

    def _reload_apps(self):
        resources = self.api.get_json('/api/lr/my-resources')
        apps = list(resources.get('applications', [])) + list(resources.get('folders', []))
        self.root.after(0, lambda: self.show_apps(apps))
