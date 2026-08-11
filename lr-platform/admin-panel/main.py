import sys
import os
import shutil
import subprocess
import tkinter as tk
import threading

from PIL import Image, ImageTk
from tkinter import messagebox, ttk

from api_client import ApiClient, ApiError
from config import APP_ID, APP_NAME, APP_VERSION, DEFAULT_BACKEND_URL, SettingsStore
from panels.assign_folder_tab import AssignFolderTab
from panels.assign_tab import AssignTab
from panels.monitor_tab import MonitorTab
from panels.printing_tab import PrintingTab
from panels.servers_tab import ServersTab
from panels.settings_tab import SettingsTab
from panels.software_tab import SoftwareTab
from panels.urls_tab import UrlsTab
from panels.users_tab import UsersTab
from panels.user_activate_license import UserActivateLicenseTab
from panels.web_portal_tab import WebPortalTab
from resources.styles import (
    BG,
    BORDER,
    HEADER_BG,
    MUTED,
    SIDEBAR,
    SIDEBAR_HOVER,
    SIDEBAR_TEXT,
    SUCCESS,
    SURFACE,
    TEXT,
    apply_style,
    button,
    resource_path,
)
from update_client import check_for_update, prompt_and_launch_update

UPDATE_CHECK_INTERVAL_MS = 10 * 60 * 1000

class AdminPanel:
    def __init__(self, root):
        self.root = root
        self.root.title('LR Admin Panel')
        self._set_initial_window_size()
        self.store = SettingsStore()
        self.settings = self.store.load()
        self.client = ApiClient(
            self.settings.get("backend_url") or DEFAULT_BACKEND_URL
)
        self.logged_in = False
        self._update_check_running = False

        apply_style(root)
        self._build()
        self.root.after(2500, self.check_for_updates_silent)

    def _set_initial_window_size(self):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = max(900, min(1220, screen_width - 120))
        height = max(560, min(700, screen_height - 130))
        x = max(10, (screen_width - width) // 2)
        y = max(10, (screen_height - height) // 2 - 10)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        self.root.minsize(min(980, width), min(580, height))

    def _load_logo(self, max_width=150):
        logo_path = resource_path('lr-remote-logo.png')
        if not logo_path.exists():
            return None

        try:
            image = Image.open(logo_path)
        except (OSError, tk.TclError):
            return None

        if image.width > max_width:
            height = max(1, int(image.height * (max_width / image.width)))
            image = image.resize((max_width, height), Image.Resampling.LANCZOS)

        return ImageTk.PhotoImage(image)

    def _build(self):
        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill=tk.BOTH, expand=True)

        sidebar = tk.Frame(shell, bg=SIDEBAR, width=218)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, bg=SIDEBAR, height=86)
        brand.pack(fill=tk.X)
        brand.pack_propagate(False)

        self.logo_image = self._load_logo()
        if self.logo_image:
            tk.Label(brand, image=self.logo_image, bg=SIDEBAR, borderwidth=0).pack(
                anchor=tk.W, padx=20, pady=(18, 4)
            )
        else:
            tk.Label(
                brand,
                text='LR  Remote Access',
                bg=SIDEBAR,
                fg='#ffffff',
                font=('Segoe UI', 14, 'bold'),
            ).pack(anchor=tk.W, padx=20, pady=(22, 4))

        content = tk.Frame(shell, bg=BG)
        content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        header = tk.Frame(
            content,
            bg=HEADER_BG,
            height=78,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        title_stack = tk.Frame(header, bg=HEADER_BG)
        title_stack.pack(side=tk.LEFT, padx=24, pady=13)
        self.page_title = tk.Label(
            title_stack,
            text='Dashboard',
            bg=HEADER_BG,
            fg=TEXT,
            font=('Segoe UI', 16, 'bold'),
        )
        self.page_title.pack(anchor=tk.W)
        self.page_subtitle = tk.Label(
            title_stack,
            text='Overview of your remote access workspace',
            bg=HEADER_BG,
            fg=MUTED,
            font=('Segoe UI', 9),
        )
        self.page_subtitle.pack(anchor=tk.W, pady=(2, 0))

        self.update_button = button(header, 'Check Update', self.check_for_updates_manual, SUCCESS)
        self.update_button.pack(side=tk.RIGHT, padx=(0, 20))

        self.login_label = tk.Label(
            header,
            text='Not logged in',
            bg=HEADER_BG,
            fg=MUTED,
            font=('Segoe UI', 9, 'bold'),
        )
        self.login_label.pack(side=tk.RIGHT, padx=18)

        self.notebook = ttk.Notebook(content, style='Sidebar.TNotebook')
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=18, pady=16)

        self.dashboard_tab = ttk.Frame(self.notebook)
        self._build_dashboard(self.dashboard_tab)

        self.users_tab = UsersTab(self.notebook, self)
        self.user_activate_license_tab = UserActivateLicenseTab(self.notebook, self)
        self.servers_tab = ServersTab(self.notebook, self)
        self.software_tab = SoftwareTab(self.notebook, self)
        self.assign_tab = AssignTab(self.notebook, self)
        self.assign_folder_tab = AssignFolderTab(self.notebook, self)
        self.urls_tab = UrlsTab(self.notebook, self)
        self.monitor_tab = MonitorTab(self.notebook, self)
        self.printing_tab = PrintingTab(self.notebook, self)
        self.web_portal_tab = WebPortalTab(self.notebook, self)
        self.settings_tab = SettingsTab(self.notebook, self)

        self.tab_specs = [
            ('dashboard', 'Dashboard', 'Overview of your remote access workspace', self.dashboard_tab),
            ('users', 'Users', 'Manage all users in the system', self.users_tab),
            ('license', 'Activate License', 'Activate and manage user licenses', self.user_activate_license_tab),
            ('servers', 'Servers', 'Manage all servers in the system', self.servers_tab),
            ('software', 'Software', 'Manage and upload software', self.software_tab),
            ('assign', 'Assign', 'Assign software to users', self.assign_tab),
            ('folders', 'Assign Folder', 'Assign folders and permissions to users', self.assign_folder_tab),
            ('urls', 'URLs', 'Create and manage allowed access URLs', self.urls_tab),
            ('monitor', 'Monitor', 'Real-time system monitoring', self.monitor_tab),
            ('printing', 'Printing', 'Manage remote printing and print jobs', self.printing_tab),
            ('web_portal', 'Web Portal', 'Customize the browser login portal', self.web_portal_tab),
            ('settings', 'Settings / Login', 'Configure application and database settings', self.settings_tab),
        ]
        self._tab_by_key = {}
        self._meta_by_widget = {}
        for key, label, subtitle, widget in self.tab_specs:
            self.notebook.add(widget, text=label)
            self._tab_by_key[key] = widget
            self._meta_by_widget[str(widget)] = (key, label, subtitle)

        nav = tk.Frame(sidebar, bg=SIDEBAR)
        nav.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 12))
        self.nav_buttons = {}
        for key, label, _subtitle, _widget in self.tab_specs:
            nav_button = tk.Button(
                nav,
                text=f'    {label}',
                command=lambda page_key=key: self.select_tab(page_key),
                bg=SIDEBAR,
                fg=SIDEBAR_TEXT,
                activebackground=SIDEBAR_HOVER,
                activeforeground='#ffffff',
                relief=tk.FLAT,
                borderwidth=0,
                highlightthickness=0,
                anchor=tk.W,
                padx=10,
                pady=6,
                cursor='hand2',
                font=('Segoe UI', 9),
            )
            nav_button.pack(fill=tk.X, pady=1)
            nav_button.bind('<Enter>', lambda _event, item=nav_button: self._hover_nav(item, True))
            nav_button.bind('<Leave>', lambda _event, item=nav_button: self._hover_nav(item, False))
            self.nav_buttons[key] = nav_button

        profile = tk.Frame(sidebar, bg='#0f2932', height=60)
        profile.pack(fill=tk.X, side=tk.BOTTOM)
        profile.pack_propagate(False)
        tk.Label(
            profile,
            text='●',
            bg='#0f2932',
            fg=SUCCESS,
            font=('Segoe UI', 13, 'bold'),
        ).pack(side=tk.LEFT, padx=(18, 9))
        profile_text = tk.Frame(profile, bg='#0f2932')
        profile_text.pack(side=tk.LEFT, pady=10)
        tk.Label(
            profile_text,
            text='Admin',
            bg='#0f2932',
            fg='#ffffff',
            font=('Segoe UI', 9, 'bold'),
        ).pack(anchor=tk.W)
        tk.Label(
            profile_text,
            text="Admin",
            bg='#0f2932',
            fg='#8fa9a1',
            font=('Segoe UI', 8),
        ).pack(anchor=tk.W)

        self.notebook.bind('<<NotebookTabChanged>>', self.on_tab_changed)

        footer = tk.Frame(content, bg=SURFACE, height=34, highlightbackground=BORDER, highlightthickness=1)
        footer.pack(fill=tk.X)
        self.status_label = tk.Label(footer, text='Ready', bg=SURFACE, fg=TEXT, anchor=tk.W, font=('Segoe UI', 9))
        self.status_label.pack(fill=tk.X, padx=12, pady=5)
        self.select_tab('dashboard')

    def _build_dashboard(self, parent):
        intro = tk.Frame(parent, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        intro.pack(fill=tk.X, padx=2, pady=(2, 14))
        tk.Label(
            intro,
            text='Remote Access Administration',
            bg=SURFACE,
            fg=TEXT,
            font=('Segoe UI', 16, 'bold'),
        ).pack(anchor=tk.W, padx=22, pady=(20, 4))
        tk.Label(
            intro,
            text='Manage users, servers, applications, licenses and system activity from one place.',
            bg=SURFACE,
            fg=MUTED,
            font=('Segoe UI', 9),
        ).pack(anchor=tk.W, padx=22, pady=(0, 20))

        card_row = tk.Frame(parent, bg=BG)
        card_row.pack(fill=tk.X)
        shortcuts = (
            ('Users', 'Manage accounts and access', 'users'),
            ('Servers', 'View connected machines', 'servers'),
            ('Software', 'Publish remote applications', 'software'),
            ('Monitor', 'Check system health', 'monitor'),
        )
        for index, (title, caption, key) in enumerate(shortcuts):
            card_row.grid_columnconfigure(index, weight=1)
            card = tk.Frame(card_row, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
            card.grid(
                row=0,
                column=index,
                sticky='nsew',
                padx=(0 if index == 0 else 6, 0 if index == len(shortcuts) - 1 else 6),
            )
            tk.Label(
                card,
                text=title,
                bg=SURFACE,
                fg=TEXT,
                font=('Segoe UI', 12, 'bold'),
            ).pack(anchor=tk.W, padx=16, pady=(16, 4))
            tk.Label(
                card,
                text=caption,
                bg=SURFACE,
                fg=MUTED,
                font=('Segoe UI', 8),
            ).pack(anchor=tk.W, padx=16)
            tk.Button(
                card,
                text='Open  >',
                command=lambda page_key=key: self.select_tab(page_key),
                bg=SURFACE,
                fg=SUCCESS,
                activebackground=SURFACE,
                activeforeground='#117f2c',
                relief=tk.FLAT,
                borderwidth=0,
                cursor='hand2',
                font=('Segoe UI', 9, 'bold'),
            ).pack(anchor=tk.W, padx=11, pady=(14, 13))

    def select_tab(self, key):
        widget = self._tab_by_key.get(key)
        if widget is not None:
            self.notebook.select(widget)
            self._update_selected_page(widget)

    def _hover_nav(self, item, entering):
        selected_path = self.notebook.select()
        selected_widget = self.notebook.nametowidget(selected_path) if selected_path else None
        selected_key = self._meta_by_widget.get(str(selected_widget), ('', '', ''))[0]
        item_key = next(
            (key for key, button_item in self.nav_buttons.items() if button_item is item),
            '',
        )
        if item_key != selected_key:
            item.configure(bg=SIDEBAR_HOVER if entering else SIDEBAR)

    def _update_selected_page(self, widget):
        key, title, subtitle = self._meta_by_widget.get(
            str(widget),
            ('dashboard', 'Dashboard', ''),
        )
        self.page_title.configure(text=title)
        self.page_subtitle.configure(text=subtitle)
        for nav_key, nav_button in self.nav_buttons.items():
            active = nav_key == key
            nav_button.configure(
                bg=SUCCESS if active else SIDEBAR,
                fg='#ffffff' if active else SIDEBAR_TEXT,
                font=('Segoe UI', 9, 'bold' if active else 'normal'),
            )

    def set_status(self, text):
        self.status_label.config(text=text)

    def _backend_url(self):
        return self.settings.get('backend_url') or DEFAULT_BACKEND_URL

    def check_for_updates_silent(self):
        self._check_for_updates(show_no_update=False)

    def check_for_updates_manual(self):
        self._check_for_updates(show_no_update=True)

    def _check_for_updates(self, show_no_update=False):
        if self._update_check_running:
            return

        self._update_check_running = True
        if show_no_update:
            self.set_status('Checking for updates...')

        def worker():
            try:
                info = check_for_update(self._backend_url(), APP_ID, APP_VERSION)
            except Exception as error:
                self.root.after(0, lambda: self._finish_update_check(None, error, show_no_update))
                return

            self.root.after(0, lambda: self._finish_update_check(info, None, show_no_update))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_update_check(self, info, error, show_no_update):
        self._update_check_running = False
        if error:
            if show_no_update:
                self.set_status('Update check failed')
                messagebox.showerror(APP_NAME, f'Update check failed: {error}')
            self._schedule_next_update_check()
            return

        if info:
            self.set_status('Update available')
            if not prompt_and_launch_update(self.root, info, APP_NAME):
                self._schedule_next_update_check()
            return

        if show_no_update:
            self.set_status('Already up to date')
            messagebox.showinfo(APP_NAME, 'Already up to date.')
        self._schedule_next_update_check()

    def _schedule_next_update_check(self):
        self.root.after(UPDATE_CHECK_INTERVAL_MS, self.check_for_updates_silent)

    def set_logged_in(self, value, username=''):
        self.logged_in = value
        self.login_label.config(fg=SUCCESS if value else MUTED)
        self.login_label.config(text=f'Logged in: {username}' if value else 'Not logged in')

    def require_login(self):
        if self.logged_in:
            return True
        messagebox.showwarning('Login Required', 'Open Settings tab and login as an Admin first.')
        self.select_tab('settings')
        return False

    def logout(self):
        try:
            self.client.logout()
        except ApiError:
            pass
        self.set_logged_in(False)
        self.set_status('Logged out')

    def refresh_all(self):
        for tab in (
            self.servers_tab,
            self.users_tab,
            self.user_activate_license_tab,
            self.software_tab,
            self.assign_tab,
            self.assign_folder_tab,
            self.urls_tab,
            self.monitor_tab,
            self.printing_tab,
            self.web_portal_tab,
        ):
            self._refresh_tab(tab)

    def _refresh_tab(self, tab):
        refresh = getattr(tab, 'refresh', None)
        if not callable(refresh):
            return
        try:
            refresh()
        except Exception as error:
            self.set_status(f'{tab.__class__.__name__} refresh failed: {error}')

    def on_tab_changed(self, _event=None):
        selected = self.notebook.nametowidget(self.notebook.select())
        self._update_selected_page(selected)
        if not self.logged_in:
            return
        if selected is not self.settings_tab:
            self._refresh_tab(selected)

    def on_users_loaded(self, users):
        self.assign_tab.update_sources(users=users)
        self.assign_folder_tab.update_sources(users=users)
        self.urls_tab.update_users(users)

    def on_apps_loaded(self, apps):
        self.assign_tab.update_sources(apps=apps)
        self.assign_folder_tab.update_sources(apps=apps)







def main():
    root = tk.Tk()
    AdminPanel(root)
    root.mainloop()


if __name__ == '__main__':
    if '--smoke-test' in sys.argv:
        raise SystemExit(0)

    import platform

    if (
        platform.system() == "Windows"
        or os.environ.get('DISPLAY')
        or os.environ.get('LR_ADMIN_XVFB')
    ):
        main()
    else:
        xvfb_run = shutil.which('xvfb-run')
        if xvfb_run:
            env = os.environ.copy()
            env['LR_ADMIN_XVFB'] = '1'
            raise SystemExit(
                subprocess.call(
                    [xvfb_run, '-a', sys.executable, os.path.abspath(__file__)],
                    env=env
                )
            )

        raise SystemExit(
            'LR Admin Panel is a Tkinter desktop app, but no display is available.\n'
            'Install Xvfb, then run this command again:\n'
            '  sudo apt-get update && sudo apt-get install -y xvfb\n'
            'Or run it from a desktop/VNC session with DISPLAY set.'
        )
