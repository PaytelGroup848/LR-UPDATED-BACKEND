import tkinter as tk
from tkinter import messagebox, ttk

from api_client import ApiError
from resources.styles import BG, BORDER, DANGER, MUTED, SUCCESS, SURFACE, TEXT, button, plain_button


class SettingsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        viewport = tk.Frame(self, bg=BG)
        viewport.pack(fill=tk.BOTH, expand=True)
        settings_canvas = tk.Canvas(viewport, bg=BG, highlightthickness=0)
        settings_scroll = ttk.Scrollbar(
            viewport,
            orient=tk.VERTICAL,
            command=settings_canvas.yview,
        )
        settings_canvas.configure(yscrollcommand=settings_scroll.set)
        settings_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        settings_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        workspace = tk.Frame(settings_canvas, bg=BG)
        workspace_window = settings_canvas.create_window(
            (0, 0),
            window=workspace,
            anchor=tk.NW,
        )
        workspace.bind(
            '<Configure>',
            lambda _event: settings_canvas.configure(
                scrollregion=settings_canvas.bbox('all'),
            ),
        )
        settings_canvas.bind(
            '<Configure>',
            lambda event: settings_canvas.itemconfigure(
                workspace_window,
                width=event.width,
            ),
        )
        settings_canvas.bind(
            '<MouseWheel>',
            lambda event: settings_canvas.yview_scroll(
                int(-event.delta / 120),
                'units',
            ),
        )
        workspace.pack_propagate(True)
        workspace.configure(padx=8, pady=8)

        left = tk.Frame(workspace, bg=BG)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))
        right = tk.Frame(workspace, bg=BG, width=285)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        right.pack_propagate(False)

        app_card, form = self._card(left, 'APPLICATION SETTINGS')
        app_card.pack(fill=tk.X, pady=(0, 12))
        form.grid_columnconfigure(1, weight=1)

        self._field_label(form, 'Backend URL', 0)
        self.backend_url = tk.StringVar(value=self.app.settings.get('backend_url', self.app.client.base_url))
        ttk.Entry(form, textvariable=self.backend_url).grid(
            row=0, column=1, sticky=tk.EW, padx=(12, 0), pady=6, ipady=6,
        )

        self._field_label(form, 'Company Code', 1)
        self.login_company_code = tk.StringVar(value=self.app.settings.get('company_code', ''))
        ttk.Entry(form, textvariable=self.login_company_code, width=32).grid(
            row=1, column=1, sticky=tk.EW, padx=(12, 0), pady=6, ipady=6,
        )

        self._field_label(form, 'Admin Username', 2)
        self.username = tk.StringVar(value=self.app.settings.get('username', ''))
        ttk.Entry(form, textvariable=self.username).grid(
            row=2, column=1, sticky=tk.EW, padx=(12, 0), pady=6, ipady=6,
        )

        self._field_label(form, 'Admin Password', 3)
        self.password = tk.StringVar()
        ttk.Entry(form, textvariable=self.password, show='*').grid(
            row=3, column=1, sticky=tk.EW, padx=(12, 0), pady=6, ipady=6,
        )

        actions = tk.Frame(form, bg=SURFACE)
        actions.grid(row=4, column=0, columnspan=2, sticky=tk.E, pady=(10, 0))
        button(actions, 'Save Settings', self.save, SUCCESS).pack(side=tk.LEFT, padx=(0, 8))
        plain_button(actions, 'Login', self.login).pack(side=tk.LEFT, padx=(0, 8))
        button(actions, 'Logout', self.logout, DANGER).pack(side=tk.LEFT, padx=(0, 8))
        plain_button(actions, 'Test Backend', self.test_backend).pack(side=tk.LEFT)

        registration_card, registration = self._card(left, 'NEW COMPANY REGISTRATION')
        registration_card.pack(fill=tk.X)
        registration.grid_columnconfigure(1, weight=1)

        self._field_label(registration, 'Company Name', 0)
        self.company_name = tk.StringVar()
        ttk.Entry(registration, textvariable=self.company_name).grid(
            row=0, column=1, sticky=tk.EW, padx=(12, 0), pady=6, ipady=6,
        )

        self._field_label(registration, 'Company Code', 1)
        self.registration_company_code = tk.StringVar()
        ttk.Entry(registration, textvariable=self.registration_company_code).grid(
            row=1, column=1, sticky=tk.EW, padx=(12, 0), pady=6, ipady=6,
        )

        self._field_label(registration, 'Email', 2)
        self.registration_email = tk.StringVar()
        ttk.Entry(registration, textvariable=self.registration_email).grid(
            row=2, column=1, sticky=tk.EW, padx=(12, 0), pady=6, ipady=6,
        )

        self._field_label(registration, 'Password', 3)
        self.registration_password = tk.StringVar()
        ttk.Entry(registration, textvariable=self.registration_password, show='*').grid(
            row=3, column=1, sticky=tk.EW, padx=(12, 0), pady=6, ipady=6,
        )

        self._field_label(registration, 'Confirm Password', 4)
        self.confirm_password = tk.StringVar()
        ttk.Entry(registration, textvariable=self.confirm_password, show='*').grid(
            row=4, column=1, sticky=tk.EW, padx=(12, 0), pady=6, ipady=6,
        )
        button(registration, 'Register Company', self.register_company, SUCCESS).grid(
            row=5, column=1, sticky=tk.W, padx=(12, 0), pady=(10, 0),
        )

        self._build_information(right)

    def _card(self, parent, title):
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
            fg=SUCCESS,
            font=('Segoe UI', 9, 'bold'),
        ).pack(anchor=tk.W, padx=16, pady=(12, 5))
        body = tk.Frame(card, bg=SURFACE)
        body.pack(fill=tk.X, padx=16, pady=(0, 14))
        return card, body

    @staticmethod
    def _field_label(parent, text, row):
        tk.Label(
            parent,
            text=text,
            bg=SURFACE,
            fg=TEXT,
            font=('Segoe UI', 9),
        ).grid(row=row, column=0, sticky=tk.W, pady=6)

    def _build_information(self, parent):
        card = tk.Frame(
            parent,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.pack(fill=tk.X)
        tk.Label(
            card,
            text='●  Information',
            bg=SURFACE,
            fg=SUCCESS,
            font=('Segoe UI', 10, 'bold'),
        ).pack(anchor=tk.W, padx=16, pady=(16, 8))
        tk.Label(
            card,
            text='Configure your application connection settings and manage company registration.',
            bg=SURFACE,
            fg=MUTED,
            justify=tk.LEFT,
            wraplength=245,
            font=('Segoe UI', 9),
        ).pack(anchor=tk.W, padx=16, pady=(0, 12))

        items = (
            ('Backend URL', 'Enter your application backend URL'),
            ('Admin Credentials', 'Set your administration login details'),
            ('Test Connection', 'Verify backend connectivity'),
            ('Company Registration', 'Register a new company to get started'),
        )
        for title, description in items:
            row = tk.Frame(card, bg=SURFACE)
            row.pack(fill=tk.X, padx=16, pady=6)
            tk.Label(
                row,
                text='✓',
                bg=SURFACE,
                fg=SUCCESS,
                font=('Segoe UI', 10, 'bold'),
            ).pack(side=tk.LEFT, anchor=tk.N, padx=(0, 8))
            text_box = tk.Frame(row, bg=SURFACE)
            text_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Label(
                text_box,
                text=title,
                bg=SURFACE,
                fg=TEXT,
                font=('Segoe UI', 9, 'bold'),
            ).pack(anchor=tk.W)
            tk.Label(
                text_box,
                text=description,
                bg=SURFACE,
                fg=MUTED,
                justify=tk.LEFT,
                wraplength=205,
                font=('Segoe UI', 8),
            ).pack(anchor=tk.W, pady=(2, 0))

        secure = tk.Frame(card, bg='#edf9f0')
        secure.pack(fill=tk.X, padx=16, pady=(14, 16))
        tk.Label(
            secure,
            text='✓  Secure & Protected',
            bg='#edf9f0',
            fg=SUCCESS,
            font=('Segoe UI', 9, 'bold'),
        ).pack(anchor=tk.W, padx=12, pady=(10, 3))
        tk.Label(
            secure,
            text='All data is encrypted and securely stored.',
            bg='#edf9f0',
            fg=MUTED,
            wraplength=215,
            justify=tk.LEFT,
            font=('Segoe UI', 8),
        ).pack(anchor=tk.W, padx=12, pady=(0, 10))

    def save(self):
        backend = self.backend_url.get().strip() or "http://191.44.87.38:8004"

        self.backend_url.set(backend)
        self.app.settings["backend_url"] = backend
        self.app.settings['company_code'] = self.login_company_code.get().strip().lower()
        self.app.settings['username'] = self.username.get().strip()
        self.app.store.save(self.app.settings)
        self.app.client.set_base_url(self.app.settings['backend_url'])
        self.app.set_status('Settings saved')
        messagebox.showinfo('Settings', 'Settings saved')

    def login(self):
        self.save()
        username = self.username.get().strip()
        company_code = self.login_company_code.get().strip()
        password = self.password.get()
        if not company_code or not username or not password:
            messagebox.showwarning('Login', 'Enter company code, admin username and password')
            return
        try:
            self.app.client.login(username, password, company_code=company_code)
            self.app.set_logged_in(True, username)
            self.app.refresh_all()
            messagebox.showinfo('Login', 'Login successful')
        except ApiError as error:
            self.app.set_logged_in(False)
            messagebox.showerror('Login', str(error))

    def logout(self):
        self.app.logout()
        self.password.set('')
        messagebox.showinfo('Logout', 'Logged out successfully')

    def register_company(self):
        self.save()
        payload = {
            'company_name': self.company_name.get().strip(),
            'company_code': self.registration_company_code.get().strip().lower(),
            'email': self.registration_email.get().strip(),
            'password': self.registration_password.get(),
            'confirm_password': self.confirm_password.get(),
        }
        if not all(payload.values()):
            messagebox.showwarning(
                'Company Registration',
                'Enter company name, company code, email, password and confirm password',
            )
            return
        if payload['password'] != payload['confirm_password']:
            messagebox.showwarning('Company Registration', 'Password and confirm password do not match')
            return
        try:
            result = self.app.client.register_company(payload)
            tenant = result.get('tenant') or {}
            company_code = tenant.get('company_code') or tenant.get('company_slug') or ''
            self.username.set(payload['email'])
            self.password.set(payload['password'])
            self.login_company_code.set(company_code)
            self.app.settings['username'] = payload['email']
            self.app.settings['company_code'] = company_code
            self.app.store.save(self.app.settings)
            self.company_name.set('')
            self.registration_company_code.set('')
            self.registration_email.set('')
            self.registration_password.set('')
            self.confirm_password.set('')
            self.app.set_status(f"Company registered: {tenant.get('company_name')}")
            messagebox.showinfo(
                'Company Registration',
                (
                    'Company and Admin created.\n\n'
                    f'Company Code: {company_code}\n'
                    'Use this Company Code with the same LR/Windows username in Desktop Client or Web View.'
                ),
            )
        except ApiError as error:
            messagebox.showerror('Company Registration', str(error))

    def test_backend(self):
        self.save()
        try:
            data = self.app.client.health()
            health = data.get('health', {})
            messagebox.showinfo('Backend', f"Connected\nStatus: {data.get('status')}\nCPU: {health.get('cpu_percent', 0)}%")
        except ApiError as error:
            messagebox.showerror('Backend', str(error))
