import tkinter as tk
from tkinter import messagebox, ttk
from html import unescape
import re

from api_client import ApiError
from dialogs import FormDialog
from resources.styles import BG, BORDER, DANGER, MUTED, PRIMARY, SUCCESS, SURFACE, TEXT, WARNING, button, plain_button


class UsersTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.users = []
        self._build()

    def _build(self):
        heading = tk.Frame(self, bg=BG)
        heading.pack(fill=tk.X, padx=8, pady=(8, 12))
        title_box = tk.Frame(heading, bg=BG)
        title_box.pack(side=tk.LEFT)
        tk.Label(
            title_box,
            text='Users',
            bg=BG,
            fg=TEXT,
            font=('Segoe UI', 15, 'bold'),
        ).pack(anchor=tk.W)
        tk.Label(
            title_box,
            text='Manage all users in the system',
            bg=BG,
            fg=MUTED,
            font=('Segoe UI', 9),
        ).pack(anchor=tk.W, pady=(3, 0))

        filters = tk.Frame(self, bg=BG)
        filters.pack(fill=tk.X, padx=8, pady=(0, 14))

        search_box = tk.Frame(
            filters,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        search_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        tk.Label(
            search_box,
            text='⌕',
            bg=SURFACE,
            fg=MUTED,
            font=('Segoe UI Symbol', 16),
        ).pack(side=tk.LEFT, padx=(12, 4))
        self.search_var = tk.StringVar(value='Search users...')
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
            font=('Segoe UI', 10),
        )
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10), ipady=10)
        self.search_entry.bind('<FocusIn>', self._search_focus_in)
        self.search_entry.bind('<FocusOut>', self._search_focus_out)
        self.search_entry.bind('<KeyRelease>', self._filter_changed)

        self.role_filter = tk.StringVar(value='All Roles')
        role_box = ttk.Combobox(
            filters,
            textvariable=self.role_filter,
            values=('All Roles', 'Admin', 'User'),
            state='readonly',
            width=15,
        )
        role_box.pack(side=tk.LEFT, ipady=7, padx=(0, 10))
        role_box.bind('<<ComboboxSelected>>', self._filter_changed)

        self.status_filter = tk.StringVar(value='All Status')
        status_box = ttk.Combobox(
            filters,
            textvariable=self.status_filter,
            values=('All Status', 'Active', 'Inactive'),
            state='readonly',
            width=15,
        )
        status_box.pack(side=tk.LEFT, ipady=7, padx=(0, 10))
        status_box.bind('<<ComboboxSelected>>', self._filter_changed)

        button(filters, '+  Add User', self.add_user, SUCCESS).pack(side=tk.RIGHT)

        columns = ('id', 'username', 'role', 'windows_session', 'active', 'last_login')
        table_card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        table_card.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        table_body = tk.Frame(table_card, bg=SURFACE)
        table_body.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(
            table_body,
            columns=columns,
            show='headings',
            selectmode='browse',
        )
        headings = {
            'id': ('ID', 70),
            'username': ('Username', 230),
            'role': ('Role', 120),
            'windows_session': ('Windows Session', 170),
            'active': ('Active', 100),
            'last_login': ('Last Login', 210),
        }
        for key, (label, width) in headings.items():
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        scrollbar = ttk.Scrollbar(table_body, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind('<Double-1>', self.open_user_details)

        footer = tk.Frame(table_card, bg=SURFACE, height=54)
        footer.pack(fill=tk.X)
        footer.pack_propagate(False)
        self.result_label = tk.Label(
            footer,
            text='Showing 0 users',
            bg=SURFACE,
            fg=MUTED,
            font=('Segoe UI', 9),
        )
        self.result_label.pack(side=tk.LEFT, padx=16)

        button(footer, 'Delete', self.delete_user, DANGER).pack(
            side=tk.RIGHT,
            padx=(0, 12),
            pady=9,
        )
        button(footer, 'Edit', self.edit_user, WARNING).pack(
            side=tk.RIGHT,
            padx=(0, 8),
            pady=9,
        )
        plain_button(footer, 'Refresh', self.refresh).pack(
            side=tk.RIGHT,
            padx=(0, 8),
            pady=9,
        )
        tk.Label(
            footer,
            text='Double-click a row to view details',
            bg=SURFACE,
            fg=MUTED,
            font=('Segoe UI', 8),
        ).pack(side=tk.RIGHT, padx=(0, 14))

    def _search_focus_in(self, _event=None):
        if not self._search_placeholder:
            return
        self.search_var.set('')
        self._search_placeholder = False
        self.search_entry.configure(fg=TEXT)

    def _search_focus_out(self, _event=None):
        if self.search_var.get().strip():
            return
        self.search_var.set('Search users...')
        self._search_placeholder = True
        self.search_entry.configure(fg=MUTED)
        self._fill()

    def _filter_changed(self, _event=None):
        self._fill()

    def refresh(self):
        if not self.app.require_login():
            return
        if getattr(self, "_is_loading", False):
            return
        self._is_loading = True

        import threading

        def worker():
            try:
                users = self.app.client.users()
                self.after(0, lambda: self._on_refreshed(users, None))
            except Exception as error:
                self.after(0, lambda: self._on_refreshed(None, error))

        threading.Thread(target=worker, daemon=True).start()

    def _on_refreshed(self, users, error):
        self._is_loading = False
        if error:
            messagebox.showerror('Users', str(error))
            self.app.set_status(f'Users load error: {error}')
            return
        self.users = users if isinstance(users, list) else []
        self._fill()
        self.app.on_users_loaded(self.users)
        self.app.set_status(f'Loaded {len(self.users)} users')

    def selected_user(self):
        selection = self.tree.selection()
        if not selection:
            return None
        values = self.tree.item(selection[0], 'values')
        if not values or not isinstance(values, (list, tuple)):
            return None
        user_id = str(values[0])
        return next((user for user in self.users if str(user.get('id')) == user_id), None)

    def add_user(self):
        try:
            servers = self.app.client.servers()
        except ApiError as error:
            messagebox.showerror('Users', f'Could not load tenant servers: {error}')
            return
        server_choices = [
            (
                f"{server.get('id')} | {server.get('name') or server.get('host')} "
                f"| Agent: {server.get('agent_status') or 'offline'}"
            )
            for server in servers
        ]
        dialog = FormDialog(self, 'Create Windows User Account', [
            {'key': 'username', 'label': 'LR and Windows username'},
            {'key': 'password', 'label': 'LR and Windows password', 'show': '*'},
            {'key': 'role', 'label': 'Role', 'values': ['User', 'Admin']},
            {'key': 'windows_domain', 'label': 'Windows domain'},
            {'key': 'windows_server', 'label': 'This company Windows server', 'values': server_choices},
            {'key': 'windows_account_enabled', 'label': 'Create and use Windows account', 'values': ['true', 'false'], 'default': 'true'},
        ])
        if not dialog.result:
            return
        payload = dict(dialog.result)
        windows_enabled = str(payload.get('windows_account_enabled', 'true')).lower() != 'false'
        windows_username = payload.get('username')
        windows_password = payload.get('password')
        server_id = ''

        if windows_enabled:
            server_value = str(payload.pop('windows_server', '') or '')
            server_id = server_value.split(' | ', 1)[0].strip()
            if not server_id:
                messagebox.showerror('Users', 'Select a tenant server with an enrolled Windows Agent')
                return
            target_server = next(
                (server for server in servers if str(server.get('id')) == server_id),
                None,
            )
            if not target_server or str(target_server.get('agent_status') or '').lower() != 'online':
                messagebox.showerror(
                    'Users',
                    (
                        'The selected server Agent is offline. Open Servers, select '
                        'the server, click Connect This Server, and wait for Agent '
                        'Status to become online.'
                    ),
                )
                return
            payload['windows_username'] = windows_username
            payload['windows_password'] = windows_password
            configured_domain = str(payload.get('windows_domain') or '').strip()
            payload['windows_account_scope'] = 'domain' if configured_domain else 'local'
            payload['server_id'] = server_id
            payload['windows_server_id'] = server_id
            payload['windows_create_account'] = 'true'
        else:
            payload.pop('windows_server', None)
            payload['windows_create_account'] = 'false'

        if not payload.get('windows_username'):
            payload.pop('windows_username', None)
        if not payload.get('windows_password'):
            payload.pop('windows_password', None)
        if not payload.get('windows_domain'):
            payload.pop('windows_domain', None)
        try:
            result = self.app.client.create_user(payload)
            self.refresh()
            server = (result or {}).get('server') or {}
            if windows_enabled:
                server_name = server.get('name') or server.get('host') or server_id
                message = f'Windows user and LR login created successfully on {server_name}'
            else:
                message = (result or {}).get('message') or 'LR user created successfully'
            messagebox.showinfo('Users', message)
        except ApiError as error:
            messagebox.showerror('Users', str(error))

    def edit_user(self):
        user = self.selected_user()
        if not user:
            messagebox.showwarning('Users', 'Select a user first')
            return
        dialog = FormDialog(self, 'Edit User', [
            {'key': 'username', 'label': 'Username'},
            {'key': 'password', 'label': 'New Password'},
            {'key': 'role', 'label': 'Role', 'values': ['User', 'Admin']},
            {'key': 'windows_username', 'label': 'Windows/RDP username'},
            {'key': 'windows_password', 'label': 'New Windows/RDP password'},
            {'key': 'windows_domain', 'label': 'Windows domain'},
            {'key': 'windows_account_enabled', 'label': 'Use Windows account', 'values': ['true', 'false']},
            {'key': 'is_active', 'label': 'Active', 'values': ['true', 'false']},
        ], {
            'username': user.get('username', ''),
            'role': user.get('role', 'User'),
            'windows_username': user.get('windows_username', ''),
            'windows_domain': user.get('windows_domain', ''),
            'windows_account_enabled': 'true' if user.get('windows_account_enabled') else 'false',
            'is_active': 'true' if user.get('is_active') else 'false',
        })
        if not dialog.result:
            return
        payload = dict(dialog.result)
        if not payload.get('password'):
            payload.pop('password', None)
        if not payload.get('windows_password'):
            payload.pop('windows_password', None)
        try:
            self.app.client.update_user(user['id'], payload)
            self.refresh()
            messagebox.showinfo('Users', 'User updated')
        except ApiError as error:
            messagebox.showerror('Users', str(error))

    def delete_user(self):
        user = self.selected_user()
        if not user:
            messagebox.showwarning('Users', 'Select a user first')
            return

        username = user.get('username')
        confirmation = (
            f"Delete LR user {username}? "
            "The remote Windows account is not deleted automatically."
        )

        if not messagebox.askyesno('Delete User', confirmation):
            return

        try:
            self.app.client.delete_user(user['id'])
            self.refresh()
            messagebox.showinfo('Users', 'User deleted')
        except ApiError as error:
            messagebox.showerror('Users', str(error))

    def open_user_details(self, _event=None):
        user = self.selected_user()
        if not user:
            return
        win = UserDetailsWindow(self, user, None)
        import threading
        def worker():
            live_data = self._load_live_user_details(user)
            self.after(0, lambda: win.update_live_data(live_data) if win.winfo_exists() else None)
        threading.Thread(target=worker, daemon=True).start()

    def _load_live_user_details(self, user):
        data = {
            'sessions': [],
            'active_session': None,
            'agent': None,
            'monitoring': {},
            'processes': [],
            'logs': [],
            'assigned_apps': [],
            'login_links': [],
            'policy': {},
            'policy_message': '',
            'policy_enforcement_status': 'not_loaded',
            'errors': [],
        }
        user_id = str(user.get('id') or '')

        try:
            data['sessions'] = self.app.client.sessions(user_id=user_id, limit=100)
            data['active_session'] = next(
                (session for session in data['sessions'] if session.get('status') == 'active'),
                data['sessions'][0] if data['sessions'] else None,
            )
        except Exception as error:
            data['errors'].append(f'Sessions: {error}')

        try:
            agent_username = user.get('windows_username') or user.get('username')
            data['agent'] = self._match_agent(user, self.app.client.agents(username=agent_username))
        except Exception as error:
            data['errors'].append(f'Agents: {error}')

        try:
            data['monitoring'] = self.app.client.monitoring()
        except Exception as error:
            data['errors'].append(f'Monitoring: {error}')

        try:
            response = self.app.client.get('/processes')
            data['processes'] = self._parse_processes(response.get('message', ''))
        except Exception as error:
            data['errors'].append(f'Processes: {error}')

        try:
            data['logs'] = self.app.client.logs(limit=50, user_id=user_id)
        except Exception as error:
            data['errors'].append(f'Logs: {error}')

        try:
            assignments = self.app.client.assignments_for_user(user_id)
            if isinstance(assignments, dict):
                data['assigned_apps'] = assignments.get('assignments') or assignments.get('apps') or []
            elif isinstance(assignments, list):
                data['assigned_apps'] = assignments
        except Exception as error:
            data['errors'].append(f'Assigned apps: {error}')

        try:
            data['login_links'] = self.app.client.login_links(user_id=user_id, limit=50)
        except Exception as error:
            data['errors'].append(f'URLs: {error}')

        try:
            policy_response = self.app.client.user_policy(user_id)
            data['policy'] = policy_response.get('policy') or {}
            data['policy_message'] = policy_response.get('message') or ''
            data['policy_enforcement_status'] = policy_response.get('enforcement_status') or 'unknown'
            data['policy_enforcement_result'] = policy_response.get('enforcement_result') or {}
        except Exception as error:
            data['errors'].append(f'Policies: {error}')

        return data

    def _match_agent(self, user, agents):
        names = {
            str(user.get('username') or '').lower(),
            str(user.get('windows_username') or '').lower(),
        }
        names.discard('')
        for agent in agents:
            if str(agent.get('username') or '').lower() in names:
                return agent
        return None

    def _parse_processes(self, process_html):
        text = unescape(re.sub(r'</?pre>', '', process_html or '', flags=re.IGNORECASE)).strip()
        processes = []
        for line in text.splitlines():
            if not line.strip() or line.startswith('Image Name') or line.startswith('='):
                continue
            match = re.match(
                r'^(?P<name>.+?)\s+(?P<pid>\d+)\s+(?P<session_name>\S+)\s+(?P<session_num>\d+)\s+(?P<memory>[\d,]+\s+K)',
                line.strip(),
            )
            if match:
                processes.append(match.groupdict())
        return processes

    def _fill(self):
        self.tree.delete(*self.tree.get_children())
        search = '' if self._search_placeholder else self.search_var.get().strip().lower()
        role_filter = self.role_filter.get()
        status_filter = self.status_filter.get()
        visible_users = []

        for user in self.users:
            role = str(user.get('role') or '')
            is_active = bool(user.get('is_active'))
            searchable = ' '.join(
                str(user.get(key) or '')
                for key in ('id', 'username', 'windows_username', 'windows_domain')
            ).lower()
            if search and search not in searchable and search not in role.lower():
                continue
            if role_filter != 'All Roles' and role.lower() != role_filter.lower():
                continue
            if status_filter == 'Active' and not is_active:
                continue
            if status_filter == 'Inactive' and is_active:
                continue
            visible_users.append(user)

        for user in visible_users:
            self.tree.insert('', tk.END, values=(
                user.get('id'),
                user.get('username', ''),
                user.get('role', ''),
                user.get('windows_username') if user.get('windows_account_configured') else 'shared',
                'Yes' if user.get('is_active') else 'No',
                user.get('last_login_at') or '',
            ))
        total = len(self.users)
        visible = len(visible_users)
        self.result_label.configure(
            text=f'Showing {visible} of {total} users' if visible != total else f'Showing {total} users'
        )


class UserDetailsWindow(tk.Toplevel):
    def __init__(self, parent, user, live_data):
        super().__init__(parent)
        self.parent_tab = parent
        self.user = user
        self.live_data = live_data or {}
        username = user.get('username') or 'User'

        self.title(f'User Details - {username}')
        self.geometry('1120x760')
        self.minsize(960, 640)
        self.configure(bg=SURFACE)
        self.transient(parent.winfo_toplevel())
        self.grab_set()

        self._build(username)
        self.update_idletasks()
        self._center(parent.winfo_toplevel())
        self.focus_set()

    def update_live_data(self, live_data):
        self.live_data = live_data or {}
        for child in self.winfo_children():
            child.destroy()
        self._build(self.user.get('username') or 'User')

    def _center(self, parent):
        parent.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def _build(self, username):
        header = tk.Frame(self, bg=SURFACE)
        header.pack(fill=tk.X, padx=18, pady=(14, 8))
        tk.Label(header, text=f'User Details - {username}', bg=SURFACE, fg=TEXT, font=('Segoe UI', 15, 'bold')).pack(side=tk.LEFT)
        status = self._status_label()
        status_color = SUCCESS if status == 'Online' else MUTED
        tk.Label(header, text=f'Status: {status}', bg=SURFACE, fg=status_color, font=('Segoe UI', 10, 'bold')).pack(side=tk.RIGHT, padx=(8, 0))
        status_dot = tk.Canvas(header, width=10, height=10, bg=SURFACE, highlightthickness=0)
        status_dot.create_oval(1, 1, 9, 9, fill=status_color, outline=status_color)
        status_dot.pack(side=tk.RIGHT)

        actions = tk.Frame(self, bg=SURFACE)
        actions.pack(fill=tk.X, padx=18, pady=(0, 10))
        button(actions, 'Remote Desktop', self._action_unavailable, SUCCESS).pack(side=tk.LEFT, padx=(0, 8))
        button(actions, 'Remote Control', self._action_unavailable, PRIMARY).pack(side=tk.LEFT, padx=(0, 8))
        button(actions, 'Send Message', self._action_unavailable, WARNING).pack(side=tk.LEFT, padx=(0, 8))
        button(actions, 'Log Off User', self._action_unavailable, DANGER).pack(side=tk.LEFT, padx=(0, 8))

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=18, pady=(0, 10))
        notebook.add(self._overview_tab(notebook), text='Overview')
        notebook.add(self._live_activity_tab(notebook), text='Live Activity')
        notebook.add(self._processes_tab(notebook), text='Processes')
        notebook.add(self._network_tab(notebook), text='Network')
        notebook.add(self._policies_tab(notebook), text='Policies')
        notebook.add(self._apps_tab(notebook), text='Apps')
        notebook.add(self._urls_tab(notebook), text='URLs')
        notebook.add(self._sessions_tab(notebook), text='Sessions')
        notebook.add(self._logs_tab(notebook), text='Logs')

        bottom = tk.Frame(self, bg=SURFACE)
        bottom.pack(fill=tk.X, padx=18, pady=(0, 14))
        button(bottom, 'Apply Policy', self._save_policy, SUCCESS).pack(side=tk.LEFT, padx=(0, 8))
        button(bottom, 'Save Changes', self._save_policy, PRIMARY).pack(side=tk.LEFT, padx=(0, 8))
        plain_button(bottom, 'Export Report', self._action_unavailable).pack(side=tk.LEFT, padx=(0, 8))
        plain_button(bottom, 'Close', self.destroy).pack(side=tk.RIGHT)

    def _overview_tab(self, parent):
        page = tk.Frame(parent, bg=BG)
        canvas = tk.Canvas(page, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(page, orient=tk.VERTICAL, command=canvas.yview)
        content = tk.Frame(canvas, bg=BG)
        content.bind('<Configure>', lambda _event: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=content, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        for column in range(3):
            content.grid_columnconfigure(column, weight=1, uniform='cards')

        active_session = self.live_data.get('active_session') or {}
        agent = self.live_data.get('agent') or {}
        assigned_apps = self.live_data.get('assigned_apps') or []
        errors = self.live_data.get('errors') or []

        cards = [
            self._info_card(content, 'User Summary', [
                ('Username', self.user.get('username', '')),
                ('User ID', self.user.get('id', '')),
                ('Role', self.user.get('role', 'User')),
                ('Windows Session', self.user.get('windows_username') or 'shared'),
                ('Active', 'Yes' if self.user.get('is_active', True) else 'No'),
                ('Last Login', self._value(self.user.get('last_login_at'))),
                ('Assigned Server', self._value(active_session.get('server_id'))),
                ('Assigned Group', self._value(self.user.get('assigned_group'))),
                ('Assigned Apps', str(len(assigned_apps)) if assigned_apps else '0'),
            ]),
            self._info_card(content, 'Device / Network Information', [
                ('Computer Name', self._value(agent.get('hostname'))),
                ('Local IP', self._value(agent.get('ip_address') or active_session.get('ip_address'))),
                ('Public IP', self._value(active_session.get('ip_address'))),
                ('MAC Address', self._not_available()),
                ('OS Version', self._value(agent.get('os'))),
                ('Windows Build', self._not_available()),
                ('Domain / Workgroup', self._value(active_session.get('windows_domain'))),
                ('Connected Network', self._not_available()),
                ('Last Seen', self._value(agent.get('last_seen') or active_session.get('last_seen_at'))),
            ]),
            self._usage_card(content),
            self._info_card(content, 'Current Activity', [
                ('Session Status', self._value(active_session.get('status'))),
                ('Published App', self._value(active_session.get('published_app_name'))),
                ('Connection Type', self._value(active_session.get('connection_type'))),
                ('Launch Mode', self._value(active_session.get('launch_mode'))),
                ('Started At', self._value(active_session.get('started_at'))),
                ('Session Duration', self._duration(active_session.get('duration_seconds'))),
                ('Last Seen', self._value(active_session.get('last_seen_at'))),
            ]),
            self._list_card(content, 'Running Applications', self._running_app_items()),
            self._process_card(content),
            self._list_card(content, 'Recent Activity', self._recent_activity_items()),
            self._quick_actions_card(content),
        ]
        if errors:
            cards.append(self._list_card(content, 'Live Data Warnings', errors))

        for index, card in enumerate(cards):
            card.grid(row=index // 3, column=index % 3, sticky='nsew', padx=8, pady=8)

        return page

    def _policies_tab(self, parent):
        self.policy_vars = {}
        page = tk.Frame(parent, bg=BG)
        for column in range(2):
            page.grid_columnconfigure(column, weight=1, uniform='policy')

        groups = [
            ('Desktop', ['Prevent Delete', 'Prevent Rename', 'Prevent Create', 'Disable Right Click', 'Lock Wallpaper', 'Hide Desktop Icons']),
            ('Explorer', ['Hide C Drive', 'Hide D Drive', 'Block Copy', 'Block Paste', 'Disable USB', 'Read Only USB']),
            ('System', ['Disable CMD', 'Disable PowerShell', 'Disable Registry', 'Disable Task Manager', 'Disable Control Panel', 'Disable Settings']),
            ('Applications', ['Allow Assigned Apps Only', 'Block Software Install', 'Block EXE Files', 'Block Games']),
            ('Browser', ['Block Downloads', 'Disable Incognito', 'Website Filtering']),
        ]
        for index, (title, items) in enumerate(groups):
            card = self._card(page, title)
            for item_index, item in enumerate(items):
                key = self._policy_key(title, item)
                var = tk.BooleanVar(value=bool((self.live_data.get('policy') or {}).get(key)))
                self.policy_vars[key] = var
                tk.Checkbutton(card, text=item, variable=var, bg=SURFACE, fg=TEXT, activebackground=SURFACE, anchor=tk.W, font=('Segoe UI', 9)).grid(
                    row=item_index // 2, column=item_index % 2, sticky='w', padx=8, pady=5
                )
            card.grid(row=index // 2, column=index % 2, sticky='nsew', padx=12, pady=12)

        status_text = (
            f"Policy status: {self.live_data.get('policy_enforcement_status') or 'unknown'}"
            f" | {self.live_data.get('policy_message') or 'No policy status from backend'}"
        )
        tk.Label(page, text=status_text, bg=BG, fg=MUTED, anchor=tk.W, font=('Segoe UI', 9, 'bold')).grid(
            row=3, column=0, columnspan=2, sticky='ew', padx=12, pady=(8, 0)
        )
        return page

    def _placeholder_tab(self, parent, title):
        page = tk.Frame(parent, bg=BG)
        tk.Label(page, text=f'{title} data will appear here.', bg=BG, fg=MUTED, font=('Segoe UI', 11, 'bold')).pack(expand=True)
        return page

    def _live_activity_tab(self, parent):
        return self._list_page(parent, 'Live Activity', self._recent_activity_items())

    def _processes_tab(self, parent):
        columns = ('name', 'pid', 'session_name', 'session_num', 'memory')
        headings = {
            'name': ('Process Name', 220),
            'pid': ('PID', 80),
            'session_name': ('Session', 110),
            'session_num': ('Session #', 90),
            'memory': ('Memory', 120),
        }
        rows = [
            (
                item.get('name') or self._not_available(),
                item.get('pid') or self._not_available(),
                item.get('session_name') or self._not_available(),
                item.get('session_num') or self._not_available(),
                item.get('memory') or self._not_available(),
            )
            for item in (self.live_data.get('processes') or [])
        ]
        return self._table_page(parent, columns, headings, rows, 'No live process data')

    def _network_tab(self, parent):
        active_session = self.live_data.get('active_session') or {}
        agent = self.live_data.get('agent') or {}
        health = (self.live_data.get('monitoring') or {}).get('health') or {}
        process = health.get('process') or {}
        rows = [
            ('Agent Hostname', self._value(agent.get('hostname'))),
            ('Agent Status', self._value(agent.get('status'))),
            ('Agent IP', self._value(agent.get('ip_address'))),
            ('Session IP', self._value(active_session.get('ip_address'))),
            ('OS', self._value(agent.get('os'))),
            ('Network Received', self._mb(process.get('network_recv_mb'))),
            ('Network Sent', self._mb(process.get('network_sent_mb'))),
            ('Last Seen', self._value(agent.get('last_seen') or active_session.get('last_seen_at'))),
        ]
        return self._key_value_page(parent, 'Network', rows)

    def _apps_tab(self, parent):
        items = []
        for app in self.live_data.get('assigned_apps') or []:
            if isinstance(app, dict):
                name = app.get('app_name') or app.get('name') or app.get('application_name') or app.get('app_id')
                status = app.get('is_enabled')
                status_text = 'enabled' if status is True else 'disabled' if status is False else 'assigned'
                items.append(f'{self._value(name)} ({status_text})')
            else:
                items.append(str(app))
        return self._list_page(parent, 'Assigned Apps', items or ['No assigned apps found'])

    def _urls_tab(self, parent):
        columns = ('id', 'created_at', 'expires_at', 'revoked_at')
        headings = {
            'id': ('Link ID', 220),
            'created_at': ('Created', 180),
            'expires_at': ('Expires', 180),
            'revoked_at': ('Revoked', 180),
        }
        rows = [
            (
                link.get('id') or self._not_available(),
                link.get('created_at') or self._not_available(),
                link.get('expires_at') or self._not_available(),
                link.get('revoked_at') or self._not_available(),
            )
            for link in (self.live_data.get('login_links') or [])
        ]
        return self._table_page(parent, columns, headings, rows, 'No login URLs found for this user')

    def _sessions_tab(self, parent):
        columns = ('id', 'status', 'app', 'started_at', 'last_seen_at', 'duration')
        headings = {
            'id': ('Session ID', 220),
            'status': ('Status', 90),
            'app': ('Published App', 170),
            'started_at': ('Started', 180),
            'last_seen_at': ('Last Seen', 180),
            'duration': ('Duration', 100),
        }
        rows = [
            (
                session.get('id') or self._not_available(),
                session.get('status') or self._not_available(),
                session.get('published_app_name') or self._not_available(),
                session.get('started_at') or self._not_available(),
                session.get('last_seen_at') or self._not_available(),
                self._duration(session.get('duration_seconds')),
            )
            for session in (self.live_data.get('sessions') or [])
        ]
        return self._table_page(parent, columns, headings, rows, 'No sessions found for this user')

    def _logs_tab(self, parent):
        columns = ('created_at', 'action', 'category', 'success', 'reason')
        headings = {
            'created_at': ('Created', 180),
            'action': ('Action', 180),
            'category': ('Category', 130),
            'success': ('Success', 80),
            'reason': ('Reason', 260),
        }
        user_id = str(self.user.get('id') or '').lower()
        rows = []
        for log in self.live_data.get('logs') or []:
            if isinstance(log, dict) and str(log.get('user_id') or '').lower() == user_id:
                rows.append((
                    log.get('created_at') or self._not_available(),
                    log.get('action') or self._not_available(),
                    log.get('category') or self._not_available(),
                    str(log.get('success')) if log.get('success') is not None else self._not_available(),
                    log.get('reason') or '',
                ))
        return self._table_page(parent, columns, headings, rows, 'No logs found for this user')

    def _table_page(self, parent, columns, headings, rows, empty_text):
        page = tk.Frame(parent, bg=BG)
        tree = ttk.Treeview(page, columns=columns, show='headings')
        for key in columns:
            label, width = headings[key]
            tree.heading(key, text=label)
            tree.column(key, width=width, anchor=tk.W)
        if rows:
            for row in rows:
                tree.insert('', tk.END, values=row)
        else:
            tree.insert('', tk.END, values=(empty_text,) + ('',) * (len(columns) - 1))
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=12, pady=12)
        scrollbar = ttk.Scrollbar(page, orient=tk.VERTICAL, command=tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=12)
        tree.configure(yscrollcommand=scrollbar.set)
        return page

    def _list_page(self, parent, title, items):
        page = tk.Frame(parent, bg=BG)
        card = self._card(page, title)
        card.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        for item in items:
            tk.Label(card, text=str(item), bg=SURFACE, fg=TEXT, anchor=tk.W, font=('Segoe UI', 9)).pack(fill=tk.X, pady=4)
        return page

    def _key_value_page(self, parent, title, rows):
        page = tk.Frame(parent, bg=BG)
        card = self._card(page, title)
        card.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
        for label, value in rows:
            self._field_row(card, label, value).pack(fill=tk.X, pady=4)
        return page

    def _card(self, parent, title):
        card = tk.LabelFrame(
            parent,
            text=title,
            bg=SURFACE,
            fg=TEXT,
            padx=12,
            pady=10,
            font=('Segoe UI', 10, 'bold'),
            highlightbackground=BORDER,
            highlightthickness=1,
            bd=0,
        )
        return card

    def _info_card(self, parent, title, rows):
        card = self._card(parent, title)
        for label, value in rows:
            self._field_row(card, label, value).pack(fill=tk.X, pady=3)
        return card

    def _usage_card(self, parent):
        card = self._card(parent, 'Live System Usage')
        health = (self.live_data.get('monitoring') or {}).get('health') or {}
        process = health.get('process') or {}
        for label, value in [
            ('CPU Usage', process.get('cpu_percent')),
            ('RAM Usage', process.get('memory_percent')),
            ('Disk Usage', process.get('disk_percent')),
        ]:
            row = tk.Frame(card, bg=SURFACE)
            tk.Label(row, text=label, bg=SURFACE, fg=TEXT, width=16, anchor=tk.W, font=('Segoe UI', 9, 'bold')).pack(side=tk.LEFT)
            progress = ttk.Progressbar(row, value=value or 0, maximum=100)
            progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
            text = f'{value}%' if value is not None else self._not_available()
            tk.Label(row, text=text, bg=SURFACE, fg=TEXT, width=12, anchor=tk.E).pack(side=tk.LEFT)
            row.pack(fill=tk.X, pady=5)
        for label, value in [
            ('Network Received', self._mb(process.get('network_recv_mb'))),
            ('Network Sent', self._mb(process.get('network_sent_mb'))),
            ('Idle Time', self._not_available()),
            ('Screen Status', self._status_label()),
        ]:
            self._field_row(card, label, value).pack(fill=tk.X, pady=3)
        return card

    def _list_card(self, parent, title, items):
        card = self._card(parent, title)
        for item in items:
            tk.Label(card, text=item, bg=SURFACE, fg=TEXT, anchor=tk.W, font=('Segoe UI', 9)).pack(fill=tk.X, pady=4)
        return card

    def _process_card(self, parent):
        card = self._card(parent, 'Top Processes')
        tree = ttk.Treeview(card, columns=('name', 'cpu', 'memory'), show='headings', height=5)
        for column, label, width in [('name', 'Process Name', 130), ('cpu', 'PID', 70), ('memory', 'Memory', 90)]:
            tree.heading(column, text=label)
            tree.column(column, width=width, anchor=tk.W)
        for process in (self.live_data.get('processes') or [])[:8]:
            tree.insert('', tk.END, values=(
                process.get('name') or self._not_available(),
                process.get('pid') or self._not_available(),
                process.get('memory') or self._not_available(),
            ))
        if not tree.get_children():
            tree.insert('', tk.END, values=('No live process data', '', ''))
        tree.pack(fill=tk.BOTH, expand=True)
        return card

    def _quick_actions_card(self, parent):
        card = self._card(parent, 'Quick Actions')
        for text in ('Kill Process', 'Block Application', 'Clear Clipboard', 'Lock Screen', 'Restart Explorer'):
            plain_button(card, text, self._action_unavailable).pack(fill=tk.X, pady=3)
        plain_button(card, 'Refresh Information', self._refresh_information).pack(fill=tk.X, pady=3)
        return card

    def _field_row(self, parent, label, value):
        row = tk.Frame(parent, bg=SURFACE)
        tk.Label(row, text=label, bg=SURFACE, fg=TEXT, width=19, anchor=tk.W, font=('Segoe UI', 9, 'bold')).pack(side=tk.LEFT)
        tk.Label(row, text=str(value), bg=SURFACE, fg=TEXT, anchor=tk.W, wraplength=220).pack(side=tk.LEFT, fill=tk.X, expand=True)
        return row

    def _status_label(self):
        active_session = self.live_data.get('active_session') or {}
        agent = self.live_data.get('agent') or {}
        if active_session.get('status') == 'active' or agent.get('status') == 'online':
            return 'Online'
        return 'Offline'

    def _running_app_items(self):
        items = []
        for session in self.live_data.get('sessions') or []:
            app_name = session.get('published_app_name')
            if app_name:
                items.append(f'{app_name} ({session.get("status") or "unknown"})')
        return items or ['No live application session data']

    def _recent_activity_items(self):
        username = str(self.user.get('username') or '').lower()
        user_id = str(self.user.get('id') or '').lower()
        items = []
        for log in self.live_data.get('logs') or []:
            text = ' '.join(str(value) for value in log.values() if value is not None).lower() if isinstance(log, dict) else str(log).lower()
            if username and username not in text and user_id and user_id not in text:
                continue
            if isinstance(log, dict):
                timestamp = log.get('created_at') or log.get('timestamp') or log.get('time') or ''
                action = log.get('action') or log.get('event') or log.get('message') or log.get('category') or 'Activity'
                items.append(f'{timestamp}  {action}'.strip())
            else:
                items.append(str(log))
            if len(items) >= 8:
                break
        return items or ['No live activity logs found']

    def _value(self, value):
        if value is None or value == '':
            return self._not_available()
        return value

    def _not_available(self):
        return 'Not available'

    def _duration(self, seconds):
        if seconds is None:
            return self._not_available()
        try:
            seconds = int(seconds)
        except (TypeError, ValueError):
            return self._not_available()
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f'{hours:02d}:{minutes:02d}:{seconds:02d}'

    def _mb(self, value):
        if value is None:
            return self._not_available()
        return f'{value} MB'

    def _policy_key(self, group, label):
        return (
            f'{group}_{label}'
            .lower()
            .replace('/', '')
            .replace(' ', '_')
            .replace('__', '_')
        )

    def _current_policy(self):
        return {
            key: bool(var.get())
            for key, var in getattr(self, 'policy_vars', {}).items()
        }

    def _save_policy(self):
        try:
            response = self.parent_tab.app.client.save_user_policy(
                self.user.get('id'),
                self._current_policy(),
            )
        except Exception as error:
            messagebox.showerror('Policies', f'Policy save failed: {error}')
            return

        self.live_data['policy'] = response.get('policy') or self._current_policy()
        self.live_data['policy_message'] = response.get('message') or ''
        self.live_data['policy_enforcement_status'] = response.get('enforcement_status') or 'saved_only'
        self.live_data['policy_enforcement_result'] = response.get('enforcement_result') or {}
        messagebox.showinfo(
            'Policies',
            f"{self.live_data['policy_enforcement_status']}: {self.live_data['policy_message'] or 'Policy saved.'}"
        )

    def _action_unavailable(self):
        messagebox.showinfo(
            'Live Action',
            'This action is not connected to a backend endpoint yet.'
        )

    def _refresh_information(self):
        live_data = self.parent_tab._load_live_user_details(self.user)
        self.destroy()
        UserDetailsWindow(self.parent_tab, self.user, live_data)
