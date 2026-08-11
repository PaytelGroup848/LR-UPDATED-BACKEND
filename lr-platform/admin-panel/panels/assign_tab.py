import ntpath
import platform
import re
import subprocess
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from api_client import ApiError
from resources.styles import BG, BORDER, DANGER, MUTED, SUCCESS, SURFACE, TEXT, button, plain_button


class AssignTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.users = []
        self.apps = []
        self.assigned_ids = set()
        self._build()

    def _build(self):
        heading = tk.Frame(self, bg=BG)
        heading.pack(fill=tk.X, padx=8, pady=(8, 12))
        tk.Label(
            heading,
            text='Assign Software',
            bg=BG,
            fg=TEXT,
            font=('Segoe UI', 15, 'bold'),
        ).pack(anchor=tk.W)
        tk.Label(
            heading,
            text='Assign software to users',
            bg=BG,
            fg=MUTED,
            font=('Segoe UI', 9),
        ).pack(anchor=tk.W, pady=(3, 0))

        workspace = tk.Frame(self, bg=BG)
        workspace.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        form_card = tk.Frame(
            workspace,
            bg=SURFACE,
            width=350,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        form_card.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 12))
        form_card.pack_propagate(False)

        form = tk.Frame(form_card, bg=SURFACE)
        form.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)
        form.grid_columnconfigure(1, weight=1)
        form.grid_rowconfigure(5, weight=1)

        self.software_var = tk.StringVar()
        self.user_var = tk.StringVar()
        self.server_var = tk.StringVar()
        self.installation_path_var = tk.StringVar()
        self.multiple_users_var = tk.BooleanVar(value=False)

        labels = (
            (0, 'Select Software'),
            (1, 'Select Server'),
            (2, 'Select User'),
            (3, 'Installation Path'),
        )
        for row, label in labels:
            tk.Label(
                form,
                text=label,
                bg=SURFACE,
                fg=TEXT,
                font=('Segoe UI', 9),
            ).grid(row=row, column=0, sticky=tk.W, padx=(0, 12), pady=10)

        self.software_combo = ttk.Combobox(
            form,
            textvariable=self.software_var,
            state='readonly',
            width=28,
        )
        self.software_combo.grid(row=0, column=1, sticky=tk.EW, pady=10, ipady=6)
        self.software_combo.bind('<<ComboboxSelected>>', self._software_selected)

        self.server_entry = ttk.Entry(
            form,
            textvariable=self.server_var,
            state='readonly',
        )
        self.server_entry.grid(row=1, column=1, sticky=tk.EW, pady=10, ipady=6)

        self.user_combo = ttk.Combobox(
            form,
            textvariable=self.user_var,
            state='readonly',
            width=28,
        )
        self.user_combo.grid(row=2, column=1, sticky=tk.EW, pady=10, ipady=6)
        self.user_combo.bind('<<ComboboxSelected>>', lambda _event: self.load_for_user())

        self.path_entry = ttk.Entry(
            form,
            textvariable=self.installation_path_var,
            state='readonly',
        )
        self.path_entry.grid(row=3, column=1, sticky=tk.EW, pady=10, ipady=6)

        ttk.Checkbutton(
            form,
            text='Assign to Multiple Users',
            variable=self.multiple_users_var,
            state='disabled',
        ).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(18, 0))
        tk.Label(
            form,
            text='Bulk assignment will be enabled when supported by the server.',
            bg=SURFACE,
            fg=MUTED,
            font=('Segoe UI', 8),
        ).grid(row=5, column=0, columnspan=2, sticky=tk.NW, pady=(5, 0))

        form_actions = tk.Frame(form, bg=SURFACE)
        form_actions.grid(row=6, column=0, columnspan=2, sticky=tk.EW, pady=(14, 0))
        plain_button(form_actions, 'Reset', self.reset_form).pack(side=tk.LEFT)
        button(form_actions, 'Assign Software', self.assign_selected, SUCCESS).pack(side=tk.RIGHT)

        lists = tk.Frame(workspace, bg=BG)
        lists.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        list_cards = tk.Frame(lists, bg=BG)
        list_cards.pack(fill=tk.BOTH, expand=True)
        list_cards.grid_rowconfigure(0, weight=1)
        list_cards.grid_columnconfigure(0, weight=1)
        list_cards.grid_columnconfigure(1, weight=1)

        assigned_card = self._list_card(list_cards, 'Assigned Software')
        assigned_card.grid(row=0, column=0, sticky='nsew', padx=(0, 6))
        available_card = self._list_card(list_cards, 'Available Software')
        available_card.grid(row=0, column=1, sticky='nsew', padx=(6, 0))

        self.assigned_tree = self._tree(assigned_card)
        self.available_tree = self._tree(available_card)
        self.available_tree.bind('<<TreeviewSelect>>', self._available_tree_selected)

        actions = tk.Frame(lists, bg=BG)
        actions.pack(fill=tk.X, pady=(10, 0))
        plain_button(actions, 'Refresh', self.refresh).pack(side=tk.RIGHT)
        button(actions, 'Remove Selected', self.remove_selected, DANGER).pack(
            side=tk.RIGHT,
            padx=(0, 8),
        )

    def _list_card(self, parent, title):
        card = tk.Frame(
            parent,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        tk.Label(
            card,
            text=title,
            bg=SURFACE,
            fg=TEXT,
            font=('Segoe UI', 10, 'bold'),
        ).pack(anchor=tk.W, padx=14, pady=(12, 4))
        return card

    def _tree(self, parent):
        tree = ttk.Treeview(parent, columns=('id', 'name'), show='headings', selectmode='browse')
        tree.heading('id', text='ID')
        tree.heading('name', text='Software')
        tree.column('id', width=60, anchor=tk.W)
        tree.column('name', width=260, anchor=tk.W)
        tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        return tree

    def _app_label(self, app):
        return f"{app.get('id')} - {app.get('name', '')}"

    def _app_from_label(self, label):
        app_id = str(label).split(' - ', 1)[0]
        return self._app_by_id(app_id)

    def _software_selected(self, _event=None):
        app = self._app_from_label(self.software_var.get())
        self._update_app_details(app)
        if not app:
            return
        app_id = str(app.get('id'))
        for row_id in self.available_tree.get_children():
            values = self.available_tree.item(row_id, 'values')
            if values and str(values[0]) == app_id:
                self.available_tree.selection_set(row_id)
                self.available_tree.focus(row_id)
                self.available_tree.see(row_id)
                break

    def _available_tree_selected(self, _event=None):
        app_id = self._selected_id(self.available_tree)
        app = self._app_by_id(app_id)
        if not app:
            return
        self.software_var.set(self._app_label(app))
        self._update_app_details(app)

    def _update_app_details(self, app):
        app = app or {}
        server = app.get('server') or {}
        server_name = (
            server.get('name')
            or app.get('server_name')
            or app.get('server_id')
            or ''
        )
        target = (
            app.get('remote_app_file_path')
            or app.get('target')
            or app.get('initial_program')
            or app.get('remote_app_program')
            or ''
        )
        self.server_var.set(str(server_name))
        self.installation_path_var.set(str(target))

    def reset_form(self):
        self.software_var.set('')
        self.server_var.set('')
        self.installation_path_var.set('')
        self.multiple_users_var.set(False)
        for tree in (self.assigned_tree, self.available_tree):
            tree.selection_remove(tree.selection())

    def refresh(self):
        if not self.app.require_login():
            return
        try:
            self.users = self.app.client.users()
            self.apps = self.app.client.apps()
            labels = [self._user_label(user) for user in self.users]
            self.user_combo['values'] = labels
            if labels:
                if self.user_var.get() not in labels:
                    self.user_var.set(labels[0])
                    self.assigned_ids.clear()
                self.load_for_user()
            else:
                self.user_var.set('')
                self.assigned_ids.clear()
                self._fill()
        except ApiError as error:
            messagebox.showerror('Assignments', str(error))

    def update_sources(self, users=None, apps=None):
        if users is not None:
            self.users = users
            labels = [self._user_label(user) for user in users]
            self.user_combo['values'] = labels
            if self.user_var.get() not in labels:
                self.user_var.set(labels[0] if labels else '')
                self.assigned_ids.clear()
        if apps is not None:
            self.apps = apps
        self._fill()

    def load_for_user(self):
        user = self.selected_user()
        if not user:
            return
        try:
            data = self.app.client.assignments_for_user(user['id'])
            self.assigned_ids = self._assigned_id_set(data)
            self.apps = data.get('available_apps', self.apps)
            self._fill()
        except ApiError as error:
            messagebox.showerror('Assignments', str(error))

    def assign_selected(self):
        user = self.selected_user()
        app_id = self._selected_id(self.available_tree)
        if not app_id:
            selected_app = self._app_from_label(self.software_var.get())
            app_id = selected_app.get('id') if selected_app else None
        if not user or not app_id:
            messagebox.showwarning('Assignments', 'Select user and software')
            return
        try:
            self.app.client.assign_app(app_id, user['id'])
            self.load_for_user()
            messagebox.showinfo('Assignments', 'Software assigned')
        except ApiError as error:
            messagebox.showerror('Assignments', str(error))

    def remove_selected(self):
        user = self.selected_user()
        app_id = self._selected_id(self.assigned_tree)
        if not user or not app_id:
            messagebox.showwarning('Assignments', 'Select assigned software')
            return
        try:
            self.app.client.unassign_app(app_id, user['id'])
            self.load_for_user()
            messagebox.showinfo('Assignments', 'Assignment removed')
        except ApiError as error:
            messagebox.showerror('Assignments', str(error))

    def selected_user(self):
        label = self.user_var.get()
        user_id = str(label).split(' - ', 1)[0]
        return next((user for user in self.users if str(user.get('id')) == user_id), None)

    def _selected_id(self, tree):
        selection = tree.selection()
        if not selection:
            return None

        return tree.item(selection[0], 'values')[0]

    def _fill(self):
        self.assigned_tree.delete(*self.assigned_tree.get_children())
        self.available_tree.delete(*self.available_tree.get_children())
        available_apps = []
        for item in self._software_apps():
            item_id = str(item.get('id') or '')
            target = self.assigned_tree if item_id in self.assigned_ids else self.available_tree
            target.insert('', tk.END, values=(item.get('id'), item.get('name', '')))
            if target is self.available_tree:
                available_apps.append(item)

        labels = [self._app_label(item) for item in available_apps]
        if hasattr(self, 'software_combo') and self.software_combo is not None:
            self.software_combo['values'] = labels
        if hasattr(self, 'software_var') and self.software_var is not None:
            if self.software_var.get() not in labels:
                self.software_var.set('')
                self._update_app_details(None)

    @staticmethod
    def _assigned_id_set(data):
        data = data if isinstance(data, dict) else {}
        values = data.get('assigned_app_ids')
        if values is None:
            values = [
                assignment.get('app_id')
                for assignment in data.get('assignments', [])
                if isinstance(assignment, dict)
            ]
        return {str(value) for value in values or [] if value}

    def _software_apps(self):
        return [
            item for item in self.apps
            if item.get('item_type') != 'folder' and not item.get('folder_path')
        ]

    def _app_by_id(self, app_id):
        return next((item for item in self._software_apps() if str(item.get('id')) == str(app_id)), None)

    def _sync_user_desktop_shortcut(self, action, user, app):
        if platform.system().lower() != 'windows':
            return

        username = self._windows_username(user)
        shortcut_name = self._safe_shortcut_name(app.get('name'))
        target_path = self._app_target(app)
        arguments = str(app.get('arguments') or '').strip()
        working_directory = str(app.get('working_directory') or '').strip()
        if working_directory.lower().endswith(('.exe', '.bat', '.cmd', '.msi')):
            working_directory = ntpath.dirname(working_directory)
        if not working_directory and '\\' in target_path:
            working_directory = ntpath.dirname(target_path)

        if not username:
            raise ApiError('Windows username is missing for selected user')
        if action != 'delete' and not target_path:
            raise ApiError('Application target path is missing')

        result = self._run_shortcut_script(
            action,
            username,
            shortcut_name,
            target_path,
            arguments,
            working_directory,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or 'PowerShell returned an error').strip()
            raise ApiError(f'Application assigned, but desktop shortcut was not created: {message}')

    def _run_shortcut_script(self, action, username, shortcut_name, target_path, arguments, working_directory):
        script = r"""param(
    [string]$action,
    [string]$username,
    [string]$shortcutName,
    [string]$targetPath,
    [string]$arguments,
    [string]$workingDirectory
)
$ErrorActionPreference = 'Stop'
if (-not $username) { throw 'Windows username is required.' }
if (-not $shortcutName) { throw 'Shortcut name is required.' }
$profileDesktop = Join-Path (Join-Path 'C:\Users' $username) 'Desktop'
$shortcutPath = Join-Path $profileDesktop ($shortcutName + '.lnk')
if ($action -eq 'delete') {
    if (Test-Path -LiteralPath $shortcutPath) {
        Remove-Item -LiteralPath $shortcutPath -Force
    }
    exit 0
}
if (-not $targetPath) { throw 'Shortcut target is required.' }
if (-not (Test-Path -LiteralPath $profileDesktop)) {
    New-Item -ItemType Directory -Path $profileDesktop -Force | Out-Null
}
$targetPath = [Environment]::ExpandEnvironmentVariables($targetPath)
$workingDirectory = [Environment]::ExpandEnvironmentVariables($workingDirectory)
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetPath
if ($arguments) { $shortcut.Arguments = $arguments }
if ($workingDirectory) { $shortcut.WorkingDirectory = $workingDirectory }
if ($targetPath.ToLowerInvariant().EndsWith('.exe') -and (Test-Path -LiteralPath $targetPath)) {
    $shortcut.IconLocation = $targetPath
}
$shortcut.Save()
if (Test-Path -LiteralPath $targetPath) {
    $aclPath = if ((Get-Item -LiteralPath $targetPath).PSIsContainer) { $targetPath } else { Split-Path -Parent $targetPath }
    if ($aclPath) {
        & icacls $aclPath /grant "$username`:(OI)(CI)RX" /T /C | Out-Null
    }
}
exit 0
"""
        script_path = None
        try:
            with tempfile.NamedTemporaryFile('w', suffix='.ps1', delete=False, encoding='utf-8') as handle:
                handle.write(script)
                script_path = handle.name
            return subprocess.run(
                [
                    'powershell',
                    '-NoProfile',
                    '-NonInteractive',
                    '-ExecutionPolicy',
                    'Bypass',
                    '-File',
                    script_path,
                    action,
                    username,
                    shortcut_name,
                    target_path,
                    arguments,
                    working_directory,
                ],
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
        finally:
            if script_path:
                try:
                    Path(script_path).unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _app_target(app):
        app = app or {}
        for key in ('remote_app_file_path', 'target', 'initial_program', 'remote_app_program'):
            value = str(app.get(key) or '').strip().strip('"')
            if value and not value.startswith('||'):
                return value
        return ''

    def _windows_username(self, user):
        value = str((user or {}).get('windows_username') or (user or {}).get('username') or '').strip()
        if '\\' in value:
            value = value.rsplit('\\', 1)[-1]
        if '@' in value:
            value = value.split('@', 1)[0]
        return value

    def _safe_shortcut_name(self, value):
        name = re.sub(r'[\\/:*?"<>|]+', ' ', str(value or '').strip())
        return re.sub(r'\s+', ' ', name).strip() or 'Application'

    def _user_label(self, user):
        return f"{user.get('id')} - {user.get('username')}"
