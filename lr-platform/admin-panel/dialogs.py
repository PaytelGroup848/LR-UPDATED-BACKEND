import tkinter as tk
from tkinter import ttk

from api_client import ApiError
from resources.styles import BORDER, MUTED, SUCCESS, SURFACE, TEXT, button, plain_button


class FormDialog(tk.Toplevel):
    def __init__(self, parent, title, fields, initial=None):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.result = None
        self.entries = {}
        self.transient(parent)
        self.grab_set()

        initial = initial or {}
        body = ttk.Frame(self, padding=18)
        body.pack(fill=tk.BOTH, expand=True)

        for row, field in enumerate(fields):
            label = field['label']
            key = field['key']
            ttk.Label(body, text=label).grid(row=row, column=0, sticky=tk.W, pady=6)
            values = field.get('values')
            if values is not None:
                widget = ttk.Combobox(body, values=values, state=field.get('state', 'readonly'), width=34)
                widget.set(initial.get(key, field.get('default', values[0] if values else '')))
            elif field.get('multiline'):
                widget = tk.Text(body, width=36, height=4)
                widget.insert('1.0', initial.get(key, field.get('default', '')))
            else:
                widget = ttk.Entry(body, width=36, show=field.get('show', ''))
                widget.insert(0, initial.get(key, field.get('default', '')))
            widget.grid(row=row, column=1, sticky=tk.EW, pady=6, padx=(12, 0))
            self.entries[key] = widget

        actions = ttk.Frame(body)
        actions.grid(row=len(fields), column=0, columnspan=2, sticky=tk.E, pady=(16, 0))
        ttk.Button(actions, text='Cancel', command=self.destroy).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(actions, text='Save', command=self._save).pack(side=tk.RIGHT)

        self.bind('<Return>', lambda _event: self._save())
        self.bind('<Escape>', lambda _event: self.destroy())
        self.wait_window(self)

    def _save(self):
        values = {}
        for key, widget in self.entries.items():
            if isinstance(widget, tk.Text):
                values[key] = widget.get('1.0', tk.END).strip()
            else:
                values[key] = widget.get().strip()
        self.result = values
        self.destroy()


class LoginDialog(tk.Toplevel):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.title('LR Admin Panel - Login')
        self.resizable(False, False)
        self.result = False
        self.transient(parent)
        self.grab_set()

        self.configure(bg='#f6faf8')

        card = tk.Frame(self, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True, padx=28, pady=28)

        body = tk.Frame(card, bg=SURFACE)
        body.pack(fill=tk.BOTH, expand=True, padx=34, pady=30)

        logo = app._load_logo()
        if logo:
            self.logo_image = logo
            tk.Label(body, image=self.logo_image, bg=SURFACE, borderwidth=0).pack(pady=(0, 12))

        tk.Label(body, text='Admin Panel', bg=SURFACE, fg=TEXT, font=('Segoe UI', 20, 'bold')).pack()
        tk.Label(body, text='Sign in to manage LR Remote Access.', bg=SURFACE, fg=MUTED, font=('Segoe UI', 10)).pack(pady=(3, 18))

        self.backend_url = tk.StringVar(value=app.settings.get('backend_url', app.client.base_url))
        self.company_code = tk.StringVar(value=app.settings.get('company_code', ''))
        self.username = tk.StringVar(value=app.settings.get('username', ''))
        self.password = tk.StringVar()

        self.backend_entry = self._field(body, 'Backend URL', self.backend_url)
        self.company_code_entry = self._field(body, 'Company Code', self.company_code)
        self.username_entry = self._field(body, 'Username', self.username)
        self.password_entry = self._field(body, 'Password', self.password, show='*')
        self.password_entry.bind('<Return>', lambda _event: self._login())

        self.error_label = tk.Label(body, text='', bg=SURFACE, fg='#d64545', wraplength=300, justify=tk.LEFT)
        self.error_label.pack(fill=tk.X, pady=(4, 0))

        actions = tk.Frame(body, bg=SURFACE)
        actions.pack(fill=tk.X, pady=(14, 0))
        plain_button(actions, 'Cancel', self.destroy).pack(side=tk.RIGHT)
        button(actions, 'Login', self._login, SUCCESS).pack(side=tk.RIGHT, padx=(0, 8))

        self.bind('<Escape>', lambda _event: self.destroy())
        self.update_idletasks()
        self._center_on_parent(parent)
        self.after(50, self._focus_first_empty)
        self.wait_window(self)

    def _field(self, parent, label, variable, show=''):
        tk.Label(parent, text=label, bg=SURFACE, fg=TEXT, font=('Segoe UI', 9, 'bold')).pack(anchor=tk.W)
        entry = ttk.Entry(parent, textvariable=variable, show=show, width=38)
        entry.pack(fill=tk.X, pady=(4, 10))
        return entry

    def _focus_first_empty(self):
        if not self.company_code.get().strip():
            self.company_code_entry.focus_set()
        elif not self.username.get().strip():
            self.username_entry.focus_set()
        else:
            self.password_entry.focus_set()

    def _center_on_parent(self, parent):
        parent.update_idletasks()
        width = self.winfo_reqwidth()
        height = self.winfo_reqheight()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        x = parent_x + max(0, (parent_width - width) // 2)
        y = parent_y + max(0, (parent_height - height) // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def _login(self):
        backend_url = self.backend_url.get().strip()
        company_code = self.company_code.get().strip()
        username = self.username.get().strip()
        password = self.password.get()

        if not backend_url or not company_code or not username or not password:
            self.error_label.config(text='Backend URL, company code, username and password are required.')
            return

        self.app.settings['backend_url'] = backend_url
        self.app.settings['company_code'] = company_code.lower()
        self.app.settings['username'] = username
        self.app.store.save(self.app.settings)
        self.app.client.set_base_url(backend_url)
        if hasattr(self.app, 'settings_tab'):
            self.app.settings_tab.backend_url.set(backend_url)
            self.app.settings_tab.login_company_code.set(company_code)
            self.app.settings_tab.username.set(username)

        try:
            self.app.client.login(username, password, company_code=company_code)
        except ApiError as error:
            self.app.set_logged_in(False)
            self.error_label.config(text=str(error))
            return

        self.app.set_logged_in(True, username)
        self.app.set_status('Login successful')
        self.result = True
        self.destroy()
