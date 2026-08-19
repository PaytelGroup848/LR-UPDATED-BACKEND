import tkinter as tk
from tkinter import messagebox, ttk

from api_client import ApiError
from dialogs import FormDialog
from resources.styles import BG, BORDER, DANGER, MUTED, SUCCESS, SURFACE, TEXT, WARNING, button, plain_button


class SoftwareTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.apps = []
        self.servers = []
        self._build()

    def _build(self):
        heading = tk.Frame(self, bg=BG)
        heading.pack(fill=tk.X, padx=8, pady=(8, 14))
        title_box = tk.Frame(heading, bg=BG)
        title_box.pack(side=tk.LEFT)
        tk.Label(
            title_box,
            text='Software',
            bg=BG,
            fg=TEXT,
            font=('Segoe UI', 15, 'bold'),
        ).pack(anchor=tk.W)
        tk.Label(
            title_box,
            text='Manage and upload software',
            bg=BG,
            fg=MUTED,
            font=('Segoe UI', 9),
        ).pack(anchor=tk.W, pady=(3, 0))
        button(heading, '+  Add Software', self.add_software, SUCCESS).pack(
            side=tk.RIGHT,
            pady=2,
        )

        columns = ('id', 'name', 'server', 'target', 'collection', 'rds_status', 'active')
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
            show='headings',
            selectmode='browse',
        )
        widths = {
            'id': 70, 'name': 170, 'server': 150, 'target': 300,
            'collection': 160, 'rds_status': 105, 'active': 65,
        }
        labels = {
            'id': 'ID', 'name': 'Name', 'server': 'Server',
            'target': 'Executable / Alias', 'collection': 'RDS Collection',
            'rds_status': 'RemoteApp Status', 'active': 'Active',
        }
        for key in columns:
            self.tree.heading(key, text=labels[key])
            self.tree.column(key, width=widths[key], anchor=tk.W)
        self.tree.grid(row=0, column=0, sticky='nsew')
        vertical_scroll = ttk.Scrollbar(
            table_body,
            orient=tk.VERTICAL,
            command=self.tree.yview,
        )
        vertical_scroll.grid(row=0, column=1, sticky='ns')
        horizontal_scroll = ttk.Scrollbar(
            table_body,
            orient=tk.HORIZONTAL,
            command=self.tree.xview,
        )
        horizontal_scroll.grid(row=1, column=0, sticky='ew')
        self.tree.configure(
            yscrollcommand=vertical_scroll.set,
            xscrollcommand=horizontal_scroll.set,
        )

        footer = tk.Frame(table_card, bg=SURFACE, height=56)
        footer.pack(fill=tk.X)
        footer.pack_propagate(False)
        self.result_label = tk.Label(
            footer,
            text='Showing 0 software items',
            bg=SURFACE,
            fg=MUTED,
            font=('Segoe UI', 9),
        )
        self.result_label.pack(side=tk.LEFT, padx=16)
        button(footer, 'Delete', self.delete_software, DANGER).pack(
            side=tk.RIGHT,
            padx=(0, 12),
            pady=10,
        )
        button(footer, 'Edit', self.edit_software, WARNING).pack(
            side=tk.RIGHT,
            padx=(0, 8),
            pady=10,
        )
        plain_button(footer, 'Retry RemoteApp', self.retry_remote_app).pack(
            side=tk.RIGHT,
            padx=(0, 8),
            pady=10,
        )
        plain_button(footer, 'Refresh', self.refresh).pack(
            side=tk.RIGHT,
            padx=(0, 8),
            pady=10,
        )

    def refresh(self):
        if not self.app.require_login():
            return
        if getattr(self, "_is_loading", False):
            return
        self._is_loading = True

        import threading

        def worker():
            try:
                servers = self.app.client.servers()
                apps = self.app.client.apps()
                self.after(0, lambda: self._on_refreshed(servers, apps, None))
            except Exception as error:
                self.after(0, lambda: self._on_refreshed(None, None, error))

        threading.Thread(target=worker, daemon=True).start()

    def _on_refreshed(self, servers, apps, error):
        self._is_loading = False
        if error:
            messagebox.showerror('Software', str(error))
            self.app.set_status(f'Software load error: {error}')
            return
        self.servers = servers if isinstance(servers, list) else []
        self.apps = apps if isinstance(apps, list) else []
        self._fill()
        self.app.on_apps_loaded(self.apps)
        self.app.set_status(f'Loaded {len(self.apps)} software items')

    def selected_app(self):
        selection = self.tree.selection()
        if not selection:
            return None
        values = self.tree.item(selection[0], 'values')
        if not values or not isinstance(values, (list, tuple)):
            return None
        app_id = str(values[0])
        return next((item for item in self.apps if str(item.get('id')) == app_id), None)

    def add_software(self):
        self._save_dialog('Add Software')

    def edit_software(self):
        item = self.selected_app()
        if not item:
            messagebox.showwarning('Software', 'Select software first')
            return
        self._save_dialog('Edit Software', item)

    def delete_software(self):
        item = self.selected_app()
        if not item:
            messagebox.showwarning('Software', 'Select software first')
            return
        if not messagebox.askyesno('Delete Software', f"Delete {item.get('name')}?"):
            return
        try:
            result = self.app.client.delete_app(item['id'])
            self.refresh()
            messagebox.showinfo('Software', result.get('message') or 'Software deleted')
        except ApiError as error:
            messagebox.showerror('Software', str(error))

    def retry_remote_app(self):
        item = self.selected_app()
        if not item:
            messagebox.showwarning('Software', 'Select software first')
            return
        try:
            result = self.app.client.retry_remote_app(item['id'])
            self.refresh()
            message = result.get('message') or 'RemoteApp sync finished'
            if result.get('success'):
                messagebox.showinfo('RemoteApp', message)
            else:
                messagebox.showwarning('RemoteApp', message)
        except ApiError as error:
            messagebox.showerror('RemoteApp', str(error))

    def _save_dialog(self, title, item=None):
        if not self.servers:
            try:
                self.servers = self.app.client.servers()
            except ApiError as error:
                messagebox.showerror('Software', str(error))
                return
        if not self.servers:
            messagebox.showwarning('Software', 'No server found. Add an RDP server in backend first.')
            return

        server_labels = [self._server_label(server) for server in self.servers]
        selected_server = self._server_by_id(item.get('server_id')) if item else self.servers[0]
        selected_server = selected_server or self.servers[0]
        initial = {
            'server': self._server_label(selected_server),
            'name': item.get('name', '') if item else '',
            'remote_app_file_path': self._file_path(item) if item else '',
            'remote_app_alias': self._alias(item) if item else '',
            'rds_collection_name': (
                item.get('rds_collection_name') if item else selected_server.get('rds_collection_name')
            ) or '',
            'rds_connection_broker': (
                item.get('rds_connection_broker') if item else selected_server.get('rds_connection_broker')
            ) or '',
            'working_directory': item.get('working_directory') or '' if item else '',
            'arguments': item.get('arguments') or '' if item else '',
            'description': item.get('description') or '' if item else '',
            'is_active': 'true' if not item or item.get('is_active') else 'false',
        }
        dialog = FormDialog(self, title, [
            {'key': 'server', 'label': 'Server', 'values': server_labels},
            {'key': 'name', 'label': 'Software Name'},
            {'key': 'remote_app_file_path', 'label': 'Executable Path on RDS Host'},
            {'key': 'remote_app_alias', 'label': 'RemoteApp Alias (optional)'},
            {'key': 'rds_collection_name', 'label': 'RDS Collection (blank = auto)'},
            {'key': 'rds_connection_broker', 'label': 'Connection Broker (blank = auto)'},
            {'key': 'working_directory', 'label': 'Working Directory'},
            {'key': 'arguments', 'label': 'Arguments'},
            {'key': 'description', 'label': 'Description', 'multiline': True},
            {'key': 'is_active', 'label': 'Active', 'values': ['true', 'false']},
        ], initial)
        if not dialog.result:
            return
        server = self._server_from_label(dialog.result.pop('server'))
        payload = dict(dialog.result)
        payload['server_id'] = server['id']
        file_path = (payload.get('remote_app_file_path') or '').strip().strip('"')
        if not payload.get('name'):
            messagebox.showwarning('Software', 'Enter Software Name')
            return
        if not file_path:
            messagebox.showwarning('Software', 'Enter the full application .exe path on the RDS server')
            return
        payload['remote_app_file_path'] = file_path
        payload['is_active'] = payload.get('is_active') == 'true'
        payload['display_mode'] = 'remote_app'
        payload['launch_mode'] = 'remote_app'
        try:
            if item:
                result = self.app.client.update_app(item['id'], payload)
            else:
                result = self.app.client.create_app(payload)
            self.refresh()
            sync = result.get('remote_app_sync') or {}
            cleanup = result.get('remote_app_cleanup') or {}
            message = result.get('message') or 'Software saved'
            if (sync and not sync.get('success')) or (cleanup and not cleanup.get('success')):
                messagebox.showwarning('Software saved - RemoteApp pending', message)
            else:
                messagebox.showinfo('Software', message)
        except ApiError as error:
            messagebox.showerror('Software', str(error))

    def _fill(self):
        self.tree.delete(*self.tree.get_children())
        for item in self.apps:
            server = item.get('server') or self._server_by_id(item.get('server_id')) or {}
            file_path = self._file_path(item)
            alias = self._alias(item)
            target = file_path or (f'||{alias}' if alias else '-')
            if file_path and alias:
                target = f'{file_path}  (||{alias})'
            status = (item.get('remote_app_publish_status') or 'legacy').strip().lower()
            status_label = {
                'published': 'Published', 'pending': 'Pending', 'failed': 'Failed',
                'unpublished': 'Unpublished', 'legacy': 'Legacy',
            }.get(status, status.title())
            self.tree.insert('', tk.END, values=(
                item.get('id'),
                item.get('name', ''),
                server.get('name', ''),
                target,
                item.get('rds_collection_name') or server.get('rds_collection_name') or 'Auto-detect',
                status_label,
                'Yes' if item.get('is_active') else 'No',
            ))
        self.result_label.configure(
            text=f'Showing {len(self.apps)} software item'
            f'{"s" if len(self.apps) != 1 else ""}'
        )

    @staticmethod
    def _file_path(item):
        item = item or {}
        for key in ('remote_app_source_file_path', 'remote_app_file_path', 'initial_program', 'target'):
            value = str(item.get(key) or '').strip()
            if '\\' in value or '/' in value or value.lower().endswith('.exe'):
                return value
        program = str(item.get('remote_app_program') or '').strip()
        if program and not program.startswith('||') and ('\\' in program or program.lower().endswith('.exe')):
            return program
        return ''

    @staticmethod
    def _alias(item):
        item = item or {}
        alias = str(item.get('remote_app_alias') or '').strip()
        if alias:
            return alias.removeprefix('||')
        program = str(item.get('remote_app_program') or '').strip()
        if program.startswith('||'):
            return program[2:]
        if program and '\\' not in program and '/' not in program and not program.lower().endswith('.exe'):
            return program
        return ''

    def _server_by_id(self, server_id):
        return next((server for server in self.servers if str(server.get('id')) == str(server_id)), None)

    def _server_label(self, server):
        if not server:
            return ''
        return f"{server.get('id')} - {server.get('name')} ({server.get('host') or server.get('ip_address')})"

    def _server_from_label(self, label):
        server_id = str(label).split(' - ', 1)[0]
        return self._server_by_id(server_id) or self.servers[0]
