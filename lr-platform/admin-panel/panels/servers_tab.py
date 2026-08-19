import ipaddress
import socket
import tkinter as tk
from tkinter import ttk, messagebox

from api_client import ApiError
from dialogs import FormDialog
from local_agent_manager import install_and_start
from machine_identity import local_machine_claim
from resources.styles import BG, BORDER, DANGER, MUTED, SUCCESS, SURFACE, TEXT, button, plain_button


class ServersTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.servers = []
        self._build()

    def _build(self):
        heading = tk.Frame(self, bg=BG)
        heading.pack(fill=tk.X, padx=8, pady=(8, 12))
        title_box = tk.Frame(heading, bg=BG)
        title_box.pack(side=tk.LEFT)
        tk.Label(
            title_box,
            text="Servers",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor=tk.W)
        tk.Label(
            title_box,
            text="Manage all servers in the system",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W, pady=(3, 0))
        button(heading, "+  Add Server", self.add_server, SUCCESS).pack(side=tk.RIGHT, pady=2)

        stats = tk.Frame(self, bg=BG)
        stats.pack(fill=tk.X, padx=8, pady=(0, 12))
        self.stat_values = {}
        stat_specs = (
            ("total", "Total Servers", TEXT),
            ("online", "Online", SUCCESS),
            ("offline", "Offline", DANGER),
            ("maintenance", "Maintenance", "#e66a16"),
        )
        for index, (key, label, color) in enumerate(stat_specs):
            stats.grid_columnconfigure(index, weight=1)
            card = tk.Frame(
                stats,
                bg=SURFACE,
                highlightbackground=BORDER,
                highlightthickness=1,
            )
            card.grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else 5, 0 if index == len(stat_specs) - 1 else 5),
            )
            tk.Label(
                card,
                text=label,
                bg=SURFACE,
                fg=MUTED,
                font=("Segoe UI", 8),
            ).pack(anchor=tk.W, padx=13, pady=(10, 2))
            value = tk.Label(
                card,
                text="0",
                bg=SURFACE,
                fg=color,
                font=("Segoe UI", 17, "bold"),
            )
            value.pack(anchor=tk.W, padx=13, pady=(0, 10))
            self.stat_values[key] = value

        search_box = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        search_box.pack(fill=tk.X, padx=8, pady=(0, 12))
        tk.Label(
            search_box,
            text="Search",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, padx=(12, 8))
        self.search_var = tk.StringVar(value="Search servers...")
        self._search_placeholder = True
        self.search_entry = tk.Entry(
            search_box,
            textvariable=self.search_var,
            bg=SURFACE,
            fg=MUTED,
            insertbackground=TEXT,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
        )
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10), ipady=9)
        self.search_entry.bind("<FocusIn>", self._search_focus_in)
        self.search_entry.bind("<FocusOut>", self._search_focus_out)
        self.search_entry.bind("<KeyRelease>", self._filter_changed)

        columns = (
            "id", "name", "host", "username", "port", "collection",
            "agent", "agent_host", "agent_status",
        )

        table_card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        table_card.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        table_body = tk.Frame(table_card, bg=SURFACE)
        table_body.pack(fill=tk.BOTH, expand=True)
        table_body.grid_rowconfigure(0, weight=1)
        table_body.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            table_body,
            columns=columns,
            show="headings",
            selectmode="browse",
        )

        for col in columns:
            self.tree.heading(col, text=col.upper())
        self.tree.column("id", width=70)
        self.tree.column("name", width=150)
        self.tree.column("host", width=170)
        self.tree.column("username", width=140)
        self.tree.column("port", width=65)
        self.tree.column("collection", width=180)
        self.tree.column("agent", width=150)
        self.tree.column("agent_host", width=150)
        self.tree.column("agent_status", width=90)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical_scroll = ttk.Scrollbar(
            table_body,
            orient=tk.VERTICAL,
            command=self.tree.yview,
        )
        vertical_scroll.grid(row=0, column=1, sticky="ns")
        horizontal_scroll = ttk.Scrollbar(
            table_body,
            orient=tk.HORIZONTAL,
            command=self.tree.xview,
        )
        horizontal_scroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(
            yscrollcommand=vertical_scroll.set,
            xscrollcommand=horizontal_scroll.set,
        )

        footer = tk.Frame(table_card, bg=SURFACE, height=56)
        footer.pack(fill=tk.X)
        footer.pack_propagate(False)
        self.result_label = tk.Label(
            footer,
            text="Showing 0 servers",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 9),
        )
        self.result_label.pack(side=tk.LEFT, padx=16)
        button(footer, "Delete", self.delete_server, DANGER).pack(
            side=tk.RIGHT,
            padx=(0, 12),
            pady=10,
        )
        button(footer, "Edit", self.edit_server, SUCCESS).pack(
            side=tk.RIGHT,
            padx=(0, 8),
            pady=10,
        )
        button(footer, "Revoke Agent", self.revoke_agent, DANGER).pack(
            side=tk.RIGHT,
            padx=(0, 8),
            pady=10,
        )
        button(footer, "Connect This Server", self.connect_this_server, SUCCESS).pack(
            side=tk.RIGHT,
            padx=(0, 8),
            pady=10,
        )
        plain_button(footer, "Refresh", self.refresh).pack(
            side=tk.RIGHT,
            padx=(0, 8),
            pady=10,
        )

    def _search_focus_in(self, _event=None):
        if not self._search_placeholder:
            return
        self.search_var.set("")
        self._search_placeholder = False
        self.search_entry.configure(fg=TEXT)

    def _search_focus_out(self, _event=None):
        if self.search_var.get().strip():
            return
        self.search_var.set("Search servers...")
        self._search_placeholder = True
        self.search_entry.configure(fg=MUTED)
        self._fill()

    def _filter_changed(self, _event=None):
        self._fill()

    def _server_status(self, server):
        status = str(server.get("status") or server.get("agent_status") or "offline").lower()
        if status in {"maintenance", "maintainance"}:
            return "maintenance"
        if status == "online":
            return "online"
        return "offline"

    def _fill(self):
        self.tree.delete(*self.tree.get_children())
        search = "" if self._search_placeholder else self.search_var.get().strip().lower()
        visible_servers = []
        counts = {"total": len(self.servers), "online": 0, "offline": 0, "maintenance": 0}

        for server in self.servers:
            counts[self._server_status(server)] += 1
            searchable = " ".join(
                str(server.get(key) or "")
                for key in (
                    "id", "name", "host", "ip_address", "username",
                    "windows_username", "agent_id", "agent_hostname", "agent_status",
                )
            ).lower()
            if not search or search in searchable:
                visible_servers.append(server)

        for key, value in counts.items():
            self.stat_values[key].configure(text=str(value))

        for server in visible_servers:
            self.tree.insert(
                "",
                tk.END,
                values=(
                    server.get("id"),
                    server.get("name"),
                    server.get("host") or server.get("ip_address"),
                    server.get("username") or server.get("windows_username") or "",
                    server.get("port") or server.get("rdp_port"),
                    server.get("rds_collection_name") or "Auto-detect",
                    server.get("agent_id") or "Not enrolled",
                    server.get("agent_hostname") or "",
                    server.get("agent_status") or "offline",
                ),
            )

        total = len(self.servers)
        visible = len(visible_servers)
        self.result_label.configure(
            text=f"Showing {visible} of {total} servers" if visible != total else f"Showing {total} servers"
        )

    def refresh(self):
        if not self.app.require_login():
            return
        if getattr(self, "_is_loading", False):
            return
        self._is_loading = True
        self.app.set_status("Loading servers...")

        import threading

        def worker():
            try:
                servers = self.app.client.servers()
                data = servers if isinstance(servers, list) else []
                self.after(0, lambda: self._on_refreshed(data, None))
            except Exception as error:
                self.after(0, lambda: self._on_refreshed(None, error))

        threading.Thread(target=worker, daemon=True).start()

    def _on_refreshed(self, data, error):
        self._is_loading = False
        if error:
            messagebox.showerror("Servers", str(error))
            self.app.set_status(f"Servers load error: {error}")
            return
        self.servers = data
        self._fill()
        self.app.set_status(f"Loaded {len(self.servers)} servers")

    def _selected_server(self):
        selected = self.tree.selection()
        if not selected:
            return None
        values = self.tree.item(selected[0]).get("values")
        if not values or not isinstance(values, (list, tuple)):
            return None
        server_id = str(values[0])
        return next(
            (item for item in self.servers if str(item.get("id")) == server_id),
            None,
        )

    def connect_this_server(self):
        server = self._selected_server()
        if not server:
            messagebox.showwarning("Connect This Server", "Select this Windows server first.")
            return

        claim = local_machine_claim()
        local_addresses = ", ".join(claim.get("ip_addresses") or []) or "unknown"
        selected_host = server.get("host") or server.get("ip_address") or "unknown"
        selected_host_normalized = selected_host.strip().lower()
        local_hostnames = {
            str(claim.get("hostname") or "").strip().lower(),
            str(claim.get("fqdn") or "").strip().lower(),
        }
        local_addresses_set = {
            str(value).strip().lower()
            for value in claim.get("ip_addresses") or []
            if value
        }
        if selected_host_normalized not in local_hostnames and selected_host_normalized not in local_addresses_set:
            try:
                selected_host_ip = str(ipaddress.ip_address(selected_host_normalized))
            except ValueError:
                selected_host_ip = None
            if selected_host_ip and selected_host_ip in local_addresses_set:
                match = True
            else:
                try:
                    resolved = {
                        str(info[4][0]).strip().lower()
                        for info in socket.getaddrinfo(selected_host_normalized, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
                        if info and info[4] and info[4][0]
                    }
                except OSError:
                    resolved = set()
                match = bool(resolved.intersection(local_addresses_set))
        else:
            match = True

        if not match:
            messagebox.showwarning(
                "Connect This Server",
                (
                    "The selected server host does not appear to be this computer, "
                    "but the Agent will still be enrolled using this machine identity.\n\n"
                    f"Server host: {selected_host}\n"
                    f"Local hostnames: {', '.join(sorted(local_hostnames or ['unknown']))}\n"
                    f"Local addresses: {local_addresses}"
                ),
            )

        if not messagebox.askyesno(
            "Connect This Server",
            (
                f"Selected server: {server.get('name') or server.get('id')} ({selected_host})\n"
                f"This computer: {claim.get('hostname')} ({local_addresses})\n\n"
                "Install and permanently start the LR Agent on THIS computer? "
                "The backend will bind the Agent to this machine identity."
            ),
        ):
            return

        self.app.set_status("Issuing machine-bound Agent enrollment...")
        try:
            enrollment = self.app.client.create_agent_enrollment_token(
                server["id"],
                claim,
            )
            success, message = install_and_start(
                self.app.client.base_url,
                enrollment.get("enrollment_token"),
            )
            if not success:
                messagebox.showerror("Connect This Server", message)
                self.app.set_status("Agent installation failed")
                return
            self.app.set_status("Agent installed; waiting for connection")
            messagebox.showinfo(
                "Connect This Server",
                (
                    f"{message}\n\n"
                    "The Agent runs as SYSTEM at Windows startup. Refresh Servers "
                    "after a few seconds and confirm Agent Status is online."
                ),
            )
            self.after(3000, self.refresh)
        except (ApiError, OSError, RuntimeError) as error:
            self.app.set_status("Agent enrollment failed")
            messagebox.showerror("Connect This Server", str(error))

    def revoke_agent(self):
        server = self._selected_server()
        if not server:
            messagebox.showwarning("Revoke Agent", "Select a server first.")
            return
        if not messagebox.askyesno(
            "Revoke Agent",
            (
                f"Revoke the Agent binding for {server.get('name') or server.get('id')}?\n\n"
                "The existing Agent will disconnect and cannot execute commands "
                "until this server is enrolled again."
            ),
        ):
            return
        try:
            self.app.client.revoke_agent_binding(server["id"])
            self.refresh()
            messagebox.showinfo("Revoke Agent", "Agent binding revoked.")
        except ApiError as error:
            messagebox.showerror("Revoke Agent", str(error))

    def add_server(self):
        dialog = FormDialog(
            self,
            "Add Server",
            [
                {"key": "name", "label": "Name"},
                {"key": "host", "label": "Host/IP"},
                {"key": "username", "label": "Username"},
                {"key": "password", "label": "Password", "show": "*"},
                {"key": "domain", "label": "Windows Hostname/Domain"},
                {"key": "port", "label": "Port", "default": "35110"},
                {"key": "agent_id", "label": "LR Agent ID (blank = auto)"},
                {"key": "rds_collection_name", "label": "RDS Collection (blank = auto)"},
                {"key": "rds_connection_broker", "label": "Connection Broker (blank = local)"},
            ],
        )

        if not dialog.result:
            return

        try:
            self.app.client.post("/add-server", dialog.result)
            self.refresh()
            messagebox.showinfo("Success", "Server Added")
        except ApiError as e:
            messagebox.showerror("Error", str(e))


    def edit_server(self):
        selected = self.tree.selection()

        if not selected:
            messagebox.showwarning("Edit", "Please select a server")
            return

        values = self.tree.item(selected[0]).get("values")
        if not values or not isinstance(values, (list, tuple)):
            return
        server_id = values[0]
        server = next((item for item in self.servers if str(item.get("id")) == str(server_id)), None)
        if not server:
            messagebox.showerror("Edit", "Selected server was not found. Refresh and try again.")
            return

        dialog = FormDialog(
            self,
            "Edit Server",
            [
                {"key": "name", "label": "Name"},
                {"key": "host", "label": "Host/IP"},
                {"key": "username", "label": "Username"},
                {"key": "password", "label": "New Password (blank = unchanged)", "show": "*"},
                {"key": "domain", "label": "Windows Hostname/Domain"},
                {"key": "port", "label": "Port"},
                {"key": "agent_id", "label": "LR Agent ID (blank = auto)"},
                {"key": "rds_collection_name", "label": "RDS Collection (blank = auto)"},
                {"key": "rds_connection_broker", "label": "Connection Broker (blank = local)"},
            ],
            {
                "name": server.get("name") or "",
                "host": server.get("host") or server.get("ip_address") or "",
                "username": server.get("username") or "",
                "password": "",
                "domain": server.get("domain") or server.get("windows_domain") or "",
                "port": server.get("port") or server.get("rdp_port") or 3389,
                "agent_id": server.get("agent_id") or "",
                "rds_collection_name": server.get("rds_collection_name") or "",
                "rds_connection_broker": server.get("rds_connection_broker") or "",
            },
        )

        if not dialog.result:
            return

        try:
            self.app.client.post(f"/update-server/{server_id}", dialog.result)
            self.refresh()
            messagebox.showinfo("Success", "Server Updated")
        except ApiError as e:
            messagebox.showerror("Error", str(e))



    def delete_server(self):
        selected = self.tree.selection()

        if not selected:
            return

        values = self.tree.item(selected[0]).get("values")
        if not values or not isinstance(values, (list, tuple)):
            return
        server_id = values[0]

        try:
            self.app.client.delete(f"/delete-server/{server_id}")
            self.refresh()
        except ApiError as e:
            messagebox.showerror("Error", str(e))
