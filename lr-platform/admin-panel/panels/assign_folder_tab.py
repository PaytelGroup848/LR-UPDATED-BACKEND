import ntpath
import platform
import re
import subprocess
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from api_client import ApiError
from resources.styles import DANGER, SUCCESS, WARNING, button, plain_button

try:
    from tkinterdnd2 import DND_FILES
except Exception:
    DND_FILES = None


class AssignFolderTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.users = []
        self.apps = []
        self.servers = []
        self.assigned_ids = set()
        self._build()

    def _build(self):
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=12, pady=12)

        ttk.Label(top, text='User').pack(side=tk.LEFT)
        self.user_var = tk.StringVar()
        self.user_combo = ttk.Combobox(top, textvariable=self.user_var, state='readonly', width=34)
        self.user_combo.pack(side=tk.LEFT, padx=8)
        self.user_combo.bind('<<ComboboxSelected>>', lambda _event: self.load_for_user())
        plain_button(top, 'Refresh', self.refresh).pack(side=tk.LEFT, padx=8)

        form = ttk.LabelFrame(self, text='Assign Folder')
        form.pack(fill=tk.X, padx=12, pady=(0, 12))

        ttk.Label(form, text='Server').grid(row=0, column=0, sticky=tk.W, padx=10, pady=8)
        self.server_var = tk.StringVar()
        self.server_combo = ttk.Combobox(form, textvariable=self.server_var, state='readonly', width=42)
        self.server_combo.grid(row=0, column=1, sticky=tk.EW, padx=10, pady=8)

        ttk.Label(form, text='Folder Name').grid(row=0, column=2, sticky=tk.W, padx=10, pady=8)
        self.name_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.name_var, width=28).grid(row=0, column=3, sticky=tk.EW, padx=10, pady=8)

        ttk.Label(form, text='Folder Path').grid(row=1, column=0, sticky=tk.W, padx=10, pady=8)
        self.path_var = tk.StringVar()
        self.path_entry = ttk.Entry(form, textvariable=self.path_var)
        self.path_entry.grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=10, pady=8)
        self.path_entry.bind('<FocusOut>', lambda _event: self._fill_name_from_path())
        self.path_entry.bind('<Control-v>', self._paste_path)
        self.path_entry.bind('<ButtonRelease-1>', lambda _event: self._fill_name_from_path())
        self._enable_drop(self.path_entry)

        plain_button(form, 'Browse Folder', self.browse_folder).grid(row=1, column=3, sticky=tk.W, padx=10, pady=8)

        ttk.Label(form, text='Permission').grid(row=2, column=0, sticky=tk.W, padx=10, pady=8)
        self.permission_var = tk.StringVar(value='read')
        permission_box = ttk.Frame(form)
        permission_box.grid(row=2, column=1, sticky=tk.W, padx=10, pady=8)
        ttk.Radiobutton(permission_box, text='Read only', variable=self.permission_var, value='read').pack(side=tk.LEFT)
        ttk.Radiobutton(permission_box, text='Write', variable=self.permission_var, value='write').pack(side=tk.LEFT, padx=(18, 0))

        form_actions = ttk.Frame(form)
        form_actions.grid(row=2, column=3, sticky=tk.W, padx=10, pady=8)
        button(form_actions, 'Add Folder', self.add_folder_item, SUCCESS).pack(side=tk.LEFT, padx=(0, 8))
        button(form_actions, 'Assign Folder', self.assign_folder_from_form, SUCCESS).pack(side=tk.LEFT)

        form.columnconfigure(1, weight=2)
        form.columnconfigure(2, weight=1)
        form.columnconfigure(3, weight=1)

        lists = ttk.Frame(self)
        lists.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        left = ttk.LabelFrame(lists, text='Assigned Folders')
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        right = ttk.LabelFrame(lists, text='Available Folders')
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))

        self.assigned_tree = self._tree(left)
        self.available_tree = self._tree(right)

        actions = ttk.Frame(self)
        actions.pack(fill=tk.X, padx=12, pady=(0, 12))
        button(actions, 'Assign Selected', self.assign_selected, SUCCESS).pack(side=tk.LEFT, padx=(0, 8))
        button(actions, 'Remove Selected', self.remove_selected, DANGER).pack(side=tk.LEFT, padx=(0, 8))
        button(actions, 'Delete Folder Item', self.delete_folder_item, WARNING).pack(side=tk.LEFT)

    def _tree(self, parent):
        columns = ('id', 'name', 'permission', 'path')
        tree = ttk.Treeview(parent, columns=columns, show='headings', selectmode='browse')
        labels = {'id': 'ID', 'name': 'Folder', 'permission': 'Permission', 'path': 'Path'}
        widths = {'id': 70, 'name': 170, 'permission': 95, 'path': 310}
        for key in columns:
            tree.heading(key, text=labels[key])
            tree.column(key, width=widths[key], anchor=tk.W)
        tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        return tree

    def refresh(self):
        if not self.app.require_login():
            return
        try:
            self.users = self.app.client.users()
            self.servers = self.app.client.servers()
            self.apps = self.app.client.apps()
            self.user_combo['values'] = [self._user_label(user) for user in self.users]
            self.server_combo['values'] = [self._server_label(server) for server in self.servers]
            if self.servers and not self.server_var.get():
                self.server_var.set(self._server_label(self.servers[0]))
            user_labels = [self._user_label(user) for user in self.users]
            if user_labels:
                if self.user_var.get() not in user_labels:
                    self.user_var.set(user_labels[0])
                    self.assigned_ids.clear()
                self.load_for_user()
            else:
                self.user_var.set('')
                self.assigned_ids.clear()
                self._fill()
            self.app.set_status('Folder assignments loaded')
        except ApiError as error:
            messagebox.showerror('Assign Folder', str(error))

    def update_sources(self, users=None, apps=None, servers=None):
        if users is not None:
            self.users = users
            labels = [self._user_label(user) for user in users]
            self.user_combo['values'] = labels
            if self.user_var.get() not in labels:
                self.user_var.set(labels[0] if labels else '')
                self.assigned_ids.clear()
        if apps is not None:
            self.apps = apps
        if servers is not None:
            self.servers = servers
            self.server_combo['values'] = [self._server_label(server) for server in servers]
            if servers and not self.server_var.get():
                self.server_var.set(self._server_label(servers[0]))
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
            messagebox.showerror('Assign Folder', str(error))

    def browse_folder(self):
        path = filedialog.askdirectory(title='Select server folder', initialdir=self.path_var.get() or None)
        if path:
            self.path_var.set(path.replace('/', '\\'))
            self._fill_name_from_path()

    def add_folder_item(self):
        server = self.selected_server()
        path = self.path_var.get().strip().strip('"')
        permission = self.permission_var.get().strip() or 'read'
        name = self.name_var.get().strip() or self._name_from_path(path)

        if not server or not path or not name:
            messagebox.showwarning('Assign Folder', 'Select server and folder path')
            return

        try:
            folder = self._find_folder(path, permission)
            if folder:
                messagebox.showinfo('Assign Folder', 'Folder item already exists')
                return

            result = self.app.client.create_app(self._folder_payload(server, name, path, permission))
            folder = (result or {}).get('app') or self._find_folder(path, permission)
            if not folder:
                raise ApiError('Folder item was not created')

            self.path_var.set('')
            self.name_var.set('')
            self.refresh()
            messagebox.showinfo('Assign Folder', 'Folder item added')
        except ApiError as error:
            messagebox.showerror('Assign Folder', str(error))

    def assign_folder_from_form(self):
        user = self.selected_user()
        path = self.path_var.get().strip().strip('"')
        permission = self.permission_var.get().strip() or 'read'
        if not user or not path:
            messagebox.showwarning('Assign Folder', 'Select user and folder path')
            return

        folder = self._find_folder(path, permission)
        if not folder:
            messagebox.showwarning('Assign Folder', 'Add this folder first, then assign it')
            return

        try:
            self.app.client.assign_app(folder['id'], user['id'])
            self.path_var.set('')
            self.name_var.set('')
            self.load_for_user()
            messagebox.showinfo('Assign Folder', 'Folder assigned')
        except ApiError as error:
            messagebox.showerror('Assign Folder', str(error))

    def assign_selected(self):
        user = self.selected_user()
        folder_id = self._selected_id(self.available_tree)
        if not user or not folder_id:
            messagebox.showwarning('Assign Folder', 'Select user and folder')
            return
        try:
            self.app.client.assign_app(folder_id, user['id'])
            self.load_for_user()
            messagebox.showinfo('Assign Folder', 'Folder assigned')
        except ApiError as error:
            messagebox.showerror('Assign Folder', str(error))

    def remove_selected(self):
        user = self.selected_user()
        folder_id = self._selected_id(self.assigned_tree)
        if not user or not folder_id:
            messagebox.showwarning('Assign Folder', 'Select assigned folder')
            return
        try:
            self.app.client.unassign_app(folder_id, user['id'])
            self.load_for_user()
            messagebox.showinfo('Assign Folder', 'Folder assignment removed')
        except ApiError as error:
            messagebox.showerror('Assign Folder', str(error))

    def delete_folder_item(self):
        folder_id = self._selected_id(self.available_tree) or self._selected_id(self.assigned_tree)
        if not folder_id:
            messagebox.showwarning('Assign Folder', 'Select a folder item')
            return
        if not messagebox.askyesno('Assign Folder', 'Delete this folder item for all users?'):
            return
        try:
            self.app.client.delete_app(folder_id)
            self.refresh()
            messagebox.showinfo('Assign Folder', 'Folder item deleted')
        except ApiError as error:
            messagebox.showerror('Assign Folder', str(error))

    def selected_user(self):
        label = self.user_var.get()
        user_id = str(label).split(' - ', 1)[0]
        return next((user for user in self.users if str(user.get('id')) == user_id), None)

    def selected_server(self):
        label = self.server_var.get()
        server_id = str(label).split(' - ', 1)[0]
        return next((server for server in self.servers if str(server.get('id')) == server_id), None)

    def _selected_id(self, tree):
        selection = tree.selection()
        if not selection:
            return None
        return tree.item(selection[0], 'values')[0]

    def _folder_apps(self):
        return [
            item for item in self.apps
            if item.get('item_type') == 'folder' or item.get('folder_path')
        ]

    def _find_folder(self, path, permission):
        normalized = self._normalize_path(path)
        permission = str(permission or 'read').lower()
        return next((
            item for item in self._folder_apps()
            if self._normalize_path(item.get('folder_path') or item.get('target')) == normalized
            and str(item.get('folder_permission') or 'read').lower() == permission
        ), None)

    def _folder_by_id(self, folder_id):
        return next((item for item in self._folder_apps() if str(item.get('id')) == str(folder_id)), None)

    def _folder_payload(self, server, name, path, permission):
        return {
            'server_id': server['id'],
            'name': self._folder_display_name(name, permission),
            'slug': self._folder_slug(path, permission),
            'icon': 'folder',
            'item_type': 'folder',
            'display_mode': 'remote_app',
            'launch_mode': 'initial_program',
            'target': path,
            'folder_path': path,
            'folder_permission': permission,
            'initial_program': 'explorer.exe',
            'arguments': path,
            'description': 'Assigned server folder',
            'is_active': True,
        }

    def _sync_user_desktop_shortcut(self, action, user, folder):
        if platform.system().lower() != 'windows':
            return

        username = self._windows_username(user)
        shortcut_name = self._safe_shortcut_name(folder.get('name') or self._name_from_path(folder.get('folder_path')))
        folder_path = str(folder.get('folder_path') or folder.get('target') or '').strip().strip('"')
        permission = str(folder.get('folder_permission') or 'read').strip().lower()
        if not username:
            raise ApiError('Windows username is missing for selected user')
        if action != 'delete' and not folder_path:
            raise ApiError('Folder path is missing for selected folder')

        result = self._run_shortcut_script(action, username, shortcut_name, folder_path, permission)
        if result.returncode != 0:
            message = (result.stderr or result.stdout or 'PowerShell returned an error').strip()
            raise ApiError(f'Folder assigned, but desktop shortcut was not created: {message}')

    def _run_shortcut_script(self, action, username, shortcut_name, folder_path, permission):
        script = r"""param(
    [string]$action,
    [string]$username,
    [string]$shortcutName,
    [string]$folderPath,
    [string]$folderPermission
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
if (-not $folderPath) { throw 'Folder path is required.' }
if (-not (Test-Path -LiteralPath $profileDesktop)) {
    New-Item -ItemType Directory -Path $profileDesktop -Force | Out-Null
}
$shortcutArguments = '"' + $folderPath.Trim('"') + '"'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = 'explorer.exe'
$shortcut.Arguments = $shortcutArguments
if (Test-Path -LiteralPath $folderPath -PathType Container) {
    $shortcut.WorkingDirectory = $folderPath
}
$shortcut.IconLocation = 'shell32.dll,3'
$shortcut.Save()
if (Test-Path -LiteralPath $folderPath -PathType Container) {
    $grant = if ($folderPermission -eq 'write') { 'M' } else { 'RX' }
    & icacls $folderPath /grant "$username`:(OI)(CI)$grant" /C | Out-Null
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
                    folder_path,
                    permission,
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        finally:
            if script_path:
                try:
                    Path(script_path).unlink(missing_ok=True)
                except OSError:
                    pass

    def _fill(self):
        self.assigned_tree.delete(*self.assigned_tree.get_children())
        self.available_tree.delete(*self.available_tree.get_children())
        for item in self._folder_apps():
            permission = str(item.get('folder_permission') or 'read').title()
            values = (
                item.get('id'),
                item.get('name', ''),
                permission,
                item.get('folder_path') or item.get('target') or '',
            )
            item_id = str(item.get('id') or '')
            target = self.assigned_tree if item_id in self.assigned_ids else self.available_tree
            target.insert('', tk.END, values=values)

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

    def _paste_path(self, _event=None):
        try:
            value = self.clipboard_get().strip()
        except tk.TclError:
            return None
        if value:
            self.path_var.set(value.strip('"'))
            self._fill_name_from_path()
            return 'break'
        return None

    def _enable_drop(self, widget):
        if not DND_FILES or not hasattr(widget, 'drop_target_register'):
            return
        try:
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind('<<Drop>>', self._drop_path)
        except tk.TclError:
            return

    def _drop_path(self, event):
        value = str(getattr(event, 'data', '') or '').strip()
        if value.startswith('{') and value.endswith('}'):
            value = value[1:-1]
        if value:
            self.path_var.set(value.strip('"'))
            self._fill_name_from_path()
        return 'break'

    def _fill_name_from_path(self):
        if self.name_var.get().strip():
            return
        name = self._name_from_path(self.path_var.get())
        if name:
            self.name_var.set(name)

    def _name_from_path(self, path):
        value = str(path or '').strip().rstrip('\\/')
        return ntpath.basename(value) or value

    def _folder_display_name(self, name, permission):
        suffix = 'Write' if permission == 'write' else 'Read'
        return f'{name} ({suffix})'
    

    def _folder_slug(self, path, permission):
        value = f"folder-{permission}-{self._normalize_path(path)}"
        return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-') or 'folder'

    def _normalize_path(self, path):
        return str(path or '').strip().strip('"').replace('/', '\\').rstrip('\\').lower()

    def _windows_username(self, user):
        value = str((user or {}).get('windows_username') or (user or {}).get('username') or '').strip()
        if '\\' in value:
            value = value.rsplit('\\', 1)[-1]
        if '@' in value:
            value = value.split('@', 1)[0]
        return value

    def _safe_shortcut_name(self, value):
        name = re.sub(r'[\\/:*?"<>|]+', ' ', str(value or '').strip())
        return re.sub(r'\s+', ' ', name).strip() or 'Folder'

    def _user_label(self, user):
        return f"{user.get('id')} - {user.get('username')}"

    def _server_label(self, server):
        if not server:
            return ''
        return f"{server.get('id')} - {server.get('name')} ({server.get('host') or server.get('ip_address')})"
