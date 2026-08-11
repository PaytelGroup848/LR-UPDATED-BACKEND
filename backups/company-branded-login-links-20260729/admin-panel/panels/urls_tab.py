import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from api_client import ApiError
from resources.styles import BG, BORDER, MUTED, SUCCESS, SURFACE, TEXT, button, plain_button


class UrlsTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.users = []
        self.links = []
        self.generated_url = ''
        self._build()

    def _build(self):
        heading = tk.Frame(self, bg=BG)
        heading.pack(fill=tk.X, padx=8, pady=(8, 12))
        title_box = tk.Frame(heading, bg=BG)
        title_box.pack(side=tk.LEFT)
        tk.Label(
            title_box,
            text='URLs',
            bg=BG,
            fg=TEXT,
            font=('Segoe UI', 15, 'bold'),
        ).pack(anchor=tk.W)
        tk.Label(
            title_box,
            text='Manage generated access URLs',
            bg=BG,
            fg=MUTED,
            font=('Segoe UI', 9),
        ).pack(anchor=tk.W, pady=(3, 0))
        button(heading, '+  Generate URL', self.generate, SUCCESS).pack(side=tk.RIGHT, pady=2)

        form_card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        form_card.pack(fill=tk.X, padx=8, pady=(0, 12))
        form = tk.Frame(form_card, bg=SURFACE)
        form.pack(fill=tk.X, padx=16, pady=12)

        tk.Label(form, text='Select User', bg=SURFACE, fg=TEXT).grid(
            row=0, column=0, sticky=tk.W, padx=(0, 8),
        )
        self.user_var = tk.StringVar()
        self.user_combo = ttk.Combobox(form, textvariable=self.user_var, state='readonly', width=42)
        self.user_combo.grid(row=0, column=1, sticky=tk.EW, padx=(0, 18), ipady=6)

        tk.Label(form, text='Expires Minutes', bg=SURFACE, fg=TEXT).grid(
            row=0, column=2, sticky=tk.W, padx=(0, 8),
        )
        self.expiry_var = tk.StringVar(value='60')
        ttk.Entry(form, textvariable=self.expiry_var, width=12).grid(
            row=0, column=3, sticky=tk.W, padx=(0, 18), ipady=6,
        )

        self.one_time = tk.BooleanVar(value=True)
        ttk.Checkbutton(form, text='One-time link', variable=self.one_time).grid(
            row=0, column=4, sticky=tk.W,
        )
        form.grid_columnconfigure(1, weight=1)

        generated_card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        generated_card.pack(fill=tk.X, padx=8, pady=(0, 12))
        generated_header = tk.Frame(generated_card, bg=SURFACE)
        generated_header.pack(fill=tk.X, padx=14, pady=(10, 5))
        tk.Label(
            generated_header,
            text='Generated Access URL',
            bg=SURFACE,
            fg=TEXT,
            font=('Segoe UI', 10, 'bold'),
        ).pack(side=tk.LEFT)
        plain_button(generated_header, 'Copy URL', self.copy).pack(side=tk.RIGHT)

        self.output = tk.Text(
            generated_card,
            height=4,
            wrap=tk.WORD,
            bg='#f7f9f8',
            fg=TEXT,
            relief=tk.FLAT,
            borderwidth=0,
            font=('Segoe UI', 9),
        )
        self.output.pack(fill=tk.X, padx=14, pady=(0, 12))
        self.output.insert('1.0', 'Generate a URL to view and copy it here.')
        self.output.configure(state=tk.DISABLED)

        self._build_links_table()

    def _build_links_table(self):
        table_card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        table_card.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        table_header = tk.Frame(table_card, bg=SURFACE)
        table_header.pack(fill=tk.X, padx=14, pady=(10, 6))
        tk.Label(
            table_header,
            text='Access URL History',
            bg=SURFACE,
            fg=TEXT,
            font=('Segoe UI', 10, 'bold'),
        ).pack(side=tk.LEFT)
        plain_button(table_header, 'Refresh', self.refresh).pack(side=tk.RIGHT)

        columns = ('link_id', 'user', 'link_type', 'created', 'expires', 'status')
        self.links_tree = ttk.Treeview(
            table_card,
            columns=columns,
            show='headings',
            selectmode='browse',
        )
        headings = {
            'link_id': ('Link ID', 190),
            'user': ('User', 160),
            'link_type': ('Type', 110),
            'created': ('Created On', 170),
            'expires': ('Expires On', 170),
            'status': ('Status', 100),
        }
        for key, (label, width) in headings.items():
            self.links_tree.heading(key, text=label)
            self.links_tree.column(key, width=width, anchor=tk.W)

        table_body = tk.Frame(table_card, bg=SURFACE)
        table_body.pack(fill=tk.BOTH, expand=True)
        self.links_tree.pack(in_=table_body, side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(
            table_body,
            orient=tk.VERTICAL,
            command=self.links_tree.yview,
        )
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.links_tree.configure(yscrollcommand=scrollbar.set)

        footer = tk.Frame(table_card, bg=SURFACE, height=46)
        footer.pack(fill=tk.X)
        footer.pack_propagate(False)
        self.links_count_label = tk.Label(
            footer,
            text='Showing 0 access URLs',
            bg=SURFACE,
            fg=MUTED,
            font=('Segoe UI', 9),
        )
        self.links_count_label.pack(side=tk.LEFT, padx=14)

    def _fill_links(self):
        self.links_tree.delete(*self.links_tree.get_children())
        for link in self.links:
            if link.get('revoked_at'):
                status = 'Revoked'
            elif link.get('used_at'):
                status = 'Used'
            elif link.get('is_valid') is False:
                status = 'Expired'
            else:
                status = 'Active'
            token = str(link.get('token') or link.get('id') or '')
            short_token = f'{token[:18]}...' if len(token) > 18 else token
            self.links_tree.insert('', tk.END, values=(
                short_token,
                link.get('username') or link.get('user_id') or '-',
                'One time' if link.get('one_time') else 'Reusable',
                self._format_date(link.get('created_at')),
                self._format_date(link.get('expires_at')),
                status,
            ))
        self.links_count_label.configure(text=f'Showing {len(self.links)} access URLs')

    @staticmethod
    def _format_date(value):
        if not value:
            return '-'
        try:
            parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            return parsed.astimezone().strftime('%d %b %Y, %I:%M %p')
        except (TypeError, ValueError):
            return str(value)

    def update_users(self, users):
        self.users = users or []
        self.user_combo['values'] = [self._user_label(user) for user in self.users]
        if self.users and not self.user_var.get():
            self.user_combo.current(0)

    def refresh(self):
        if not self.app.require_login():
            return
        try:
            self.update_users(self.app.client.users())
            self.links = self.app.client.login_links(limit=100)
            self._fill_links()
            self.app.set_status(f'Loaded {len(self.links)} access URLs')
        except ApiError as error:
            messagebox.showerror('URLs', str(error))

    def generate(self):
        self.generated_url = ''
        user = self.selected_user()
        if not user:
            messagebox.showwarning('URLs', 'Select a user before generating a direct login URL')
            return
        try:
            expires = max(1, int(self.expiry_var.get()))
        except ValueError:
            messagebox.showwarning('URLs', 'Expires minutes must be a number')
            return
        try:
            data = self.app.client.generate_url(user.get('id') if user else None, expires, self.one_time.get())
            url = data.get('url', '')
            download_url = data.get('download_url', '')
            self.generated_url = url

            self.output.configure(state=tk.NORMAL)
            self.output.delete('1.0', tk.END)
            self.output.insert(
                '1.0',
                f'Access URL:\n{url}\n\n'
                f'Download Desktop App:\n{download_url}\n\n'
                f'Expires in: {expires} minutes\n'
                f'User: {user.get("username")}'
            )
            self.output.configure(state=tk.DISABLED)
            try:
                self.links = self.app.client.login_links(limit=100)
                self._fill_links()
            except ApiError:
                pass
        except ApiError as error:
            messagebox.showerror('URLs', str(error))

    def copy(self):
        value = self.generated_url.strip()
        if value:
            self.clipboard_clear()
            self.clipboard_append(value)
            messagebox.showinfo('URLs', 'Access URL copied to clipboard')

    def selected_user(self):
        label = self.user_var.get()
        user_id = str(label).split(' - ', 1)[0]
        return next((user for user in self.users if str(user.get('id')) == user_id), None)

    def _user_label(self, user):
        return f"{user.get('id')} - {user.get('username')}"
