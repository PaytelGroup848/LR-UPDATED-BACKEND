import io
import re
import typing
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from urllib.parse import urlparse

from PIL import Image, ImageOps, ImageTk

from api_client import ApiError
from resources.styles import (
    BG,
    BORDER,
    DANGER,
    MUTED,
    SUCCESS,
    SURFACE,
    TEXT,
    button,
    plain_button,
)


FIELD_SECTIONS = (
    (
        "Branding",
        (
            ("company_name", "Company Name", "text"),
            ("portal_title", "Portal Title", "text"),
            ("browser_title", "Browser Page Title", "text"),
            ("primary_color", "Primary Colour", "color"),
            ("secondary_color", "Secondary Colour", "color"),
            ("accent_color", "Accent Colour", "color"),
        ),
    ),
    (
        "Login Page",
        (
            ("background_color", "Background Colour", "color"),
            ("background_overlay_opacity", "Overlay Opacity (0-1)", "text"),
            ("welcome_heading", "Welcome Heading", "text"),
            ("welcome_description", "Welcome Description", "text"),
            ("username_label", "Username Field Label", "text"),
            ("password_label", "Password Field Label", "text"),
            ("login_button_text", "Login Button Text", "text"),
            ("login_card_position", "Login Card Position", "position"),
            ("login_card_width", "Login Card Width", "text"),
            ("login_card_opacity", "Login Card Opacity", "text"),
            ("login_card_border_radius", "Card Border Radius", "text"),
            ("show_company_code", "Show Company Code", "bool"),
            ("show_remember_me", "Show Remember Me", "bool"),
            ("show_logo", "Show Logo", "bool"),
            ("show_welcome_text", "Show Welcome Text", "bool"),
        ),
    ),
    (
        "Header and Footer",
        (
            ("header_text", "Header Text", "text"),
            ("footer_text", "Footer Text", "text"),
            ("copyright_text", "Copyright Text", "text"),
            ("support_email", "Support Email", "text"),
            ("support_url", "Support URL", "text"),
            ("privacy_url", "Privacy Policy URL", "text"),
            ("terms_url", "Terms URL", "text"),
            ("show_header", "Show Header", "bool"),
            ("show_footer", "Show Footer", "bool"),
        ),
    ),
    (
        "Connection Options",
        (
            ("default_connection_mode", "Default Connection Mode", "connection"),
            ("remember_connection_preference", "Remember Connection Preference", "bool"),
            ("show_available_applications_after_login", "Show Available Apps After Login", "bool"),
        ),
    ),
)


class WebPortalTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.vars = {}
        self.asset_labels = {}
        self._loading = False
        self._dirty = False
        self._settings = {}
        self._asset_urls = {}
        self._preview_assets = {}
        self._preview_photos = []
        self._build()

    def _build(self):
        heading = tk.Frame(self, bg=BG)
        heading.pack(fill=tk.X, padx=8, pady=(8, 10))
        title_box = tk.Frame(heading, bg=BG)
        title_box.pack(side=tk.LEFT)
        tk.Label(
            title_box,
            text="Web Portal Customization",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor=tk.W)
        tk.Label(
            title_box,
            text="Customize the separate browser login portal",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
        ).pack(anchor=tk.W, pady=(3, 0))

        self.state_label = tk.Label(
            heading,
            text="Draft not loaded",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9, "bold"),
        )
        self.state_label.pack(side=tk.RIGHT, padx=(12, 0))
        plain_button(heading, "Refresh", self.refresh).pack(side=tk.RIGHT)

        actions = tk.Frame(self, bg=BG)
        actions.pack(fill=tk.X, padx=8, pady=(0, 10))
        button(actions, "Save Draft", self.save_draft, SUCCESS).pack(
            side=tk.LEFT,
            padx=(0, 8),
        )
        plain_button(actions, "Preview", self._render_preview).pack(
            side=tk.LEFT,
            padx=(0, 8),
        )
        button(actions, "Publish Changes", self.publish, SUCCESS).pack(
            side=tk.LEFT,
            padx=(0, 8),
        )
        button(actions, "Reset to Default", self.reset_to_default, DANGER).pack(
            side=tk.LEFT,
        )

        body = tk.Frame(self, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        form_card = tk.Frame(
            body,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        form_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        preview_card = tk.Frame(
            body,
            bg=SURFACE,
            width=370,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        preview_card.pack(side=tk.RIGHT, fill=tk.BOTH)
        preview_card.pack_propagate(False)

        self._build_form(form_card)
        self._build_preview(preview_card)

    def _build_form(self, parent):
        canvas = tk.Canvas(parent, bg=SURFACE, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        form = tk.Frame(canvas, bg=SURFACE)
        form_window = canvas.create_window((0, 0), window=form, anchor=tk.NW)
        form.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(form_window, width=event.width),
        )
        canvas.bind(
            "<MouseWheel>",
            lambda event: canvas.yview_scroll(int(-event.delta / 120), "units"),
        )

        for section, fields in FIELD_SECTIONS:
            self._section_title(form, section)
            for field, label, kind in fields:
                self._add_field(form, field, label, kind)
        self._build_assets_section(form)

    def _section_title(self, parent, title):
        tk.Label(
            parent,
            text=title.upper(),
            bg=SURFACE,
            fg=SUCCESS,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor=tk.W, padx=16, pady=(16, 6))

    def _add_field(self, parent, field, label, kind):
        row = tk.Frame(parent, bg=SURFACE)
        row.pack(fill=tk.X, padx=16, pady=4)
        tk.Label(
            row,
            text=label,
            bg=SURFACE,
            fg=TEXT,
            width=26,
            anchor=tk.W,
            font=("Segoe UI", 9),
        ).pack(side=tk.LEFT, padx=(0, 8))

        variable = tk.BooleanVar(value=False) if kind == "bool" else tk.StringVar()
        self.vars[field] = variable
        if kind == "bool":
            control = ttk.Checkbutton(row, variable=variable)
            control.pack(side=tk.LEFT)
        elif kind in {"position", "connection"}:
            values = (
                ("left", "center", "right")
                if kind == "position"
                else ("web", "remoteapp", "desktop")
            )
            control = ttk.Combobox(
                row,
                textvariable=variable,
                values=values,
                state="readonly",
                width=30,
            )
            control.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        elif kind == "color":
            field_box = tk.Frame(row, bg=SURFACE)
            field_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
            control = ttk.Entry(field_box, textvariable=variable)
            control.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
            plain_button(
                field_box,
                "Pick",
                lambda name=field: self._pick_color(name),
            ).pack(side=tk.LEFT, padx=(6, 0))
        else:
            control = ttk.Entry(row, textvariable=variable)
            control.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        variable.trace_add("write", self._field_changed)

    def _build_assets_section(self, parent):
        self._section_title(parent, "Images")
        specs = (
            ("logo", "Logo", "PNG/JPG/WEBP up to 2 MB"),
            ("favicon", "Favicon", "PNG/ICO up to 512 KB"),
            ("background", "Background", "PNG/JPG/WEBP up to 5 MB"),
        )
        for asset_type, label, hint in specs:
            row = tk.Frame(parent, bg=SURFACE)
            row.pack(fill=tk.X, padx=16, pady=5)
            tk.Label(
                row,
                text=label,
                bg=SURFACE,
                fg=TEXT,
                width=26,
                anchor=tk.W,
            ).pack(side=tk.LEFT, padx=(0, 8))
            plain_button(
                row,
                "Upload",
                lambda kind=asset_type: self.upload_asset(kind),
            ).pack(side=tk.LEFT)
            status = tk.Label(
                row,
                text=hint,
                bg=SURFACE,
                fg=MUTED,
                font=("Segoe UI", 8),
            )
            status.pack(side=tk.LEFT, padx=8)
            self.asset_labels[asset_type] = status
        tk.Frame(parent, bg=SURFACE, height=14).pack()

    def _build_preview(self, parent):
        tk.Label(
            parent,
            text="LIVE PREVIEW",
            bg=SURFACE,
            fg=SUCCESS,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor=tk.W, padx=14, pady=(14, 3))
        tk.Label(
            parent,
            text="Representative preview; authentication is disabled.",
            bg=SURFACE,
            fg=MUTED,
            font=("Segoe UI", 8),
        ).pack(anchor=tk.W, padx=14, pady=(0, 10))
        self.preview_host = tk.Frame(parent, bg="#e8eeeb")
        self.preview_host.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self._render_preview()

    def _value(self, field, default=""):
        variable = self.vars.get(field)
        if variable is None:
            return default
        value = variable.get()
        return default if value in (None, "") else value

    @staticmethod
    def _preview_color(value, fallback):
        value = str(value or "")
        return value if len(value) == 7 and value.startswith("#") else fallback

    def _render_preview(self):
        if not hasattr(self, "preview_host"):
            return
        for child in self.preview_host.winfo_children():
            child.destroy()
        self._preview_photos = []
        background = self._preview_color(
            self._value("background_color", "#f7f9fa"),
            "#f7f9fa",
        )
        primary = self._preview_color(
            self._value("primary_color", "#159a35"),
            "#159a35",
        )
        secondary = self._preview_color(
            self._value("secondary_color", "#0b2028"),
            "#0b2028",
        )
        browser_bar = tk.Frame(self.preview_host, bg="#eef2f1", height=35)
        browser_bar.pack(fill=tk.X)
        browser_bar.pack_propagate(False)
        if self._preview_assets.get("favicon_url"):
            favicon = self._preview_assets["favicon_url"].copy()
            favicon.thumbnail((18, 18), Image.Resampling.LANCZOS)
            favicon_photo = ImageTk.PhotoImage(favicon)
            self._preview_photos.append(favicon_photo)
            tk.Label(browser_bar, image=favicon_photo, bg="#eef2f1").pack(
                side=tk.LEFT,
                padx=(10, 5),
                pady=8,
            )
        tk.Label(
            browser_bar,
            text=self._value("browser_title", "LR Remote Access"),
            bg="#eef2f1",
            fg=TEXT,
            font=("Segoe UI", 8),
        ).pack(side=tk.LEFT, pady=8)

        stage = tk.Frame(self.preview_host, bg=background)
        stage.pack(fill=tk.BOTH, expand=True)
        if self._preview_assets.get("background_image_url"):
            width = max(self.preview_host.winfo_width(), 340)
            height = max(self.preview_host.winfo_height() - 35, 430)
            background_image = ImageOps.fit(
                self._preview_assets["background_image_url"].copy(),
                (width, height),
                method=Image.Resampling.LANCZOS,
            )
            try:
                overlay = float(self._value("background_overlay_opacity", 0))
            except (TypeError, ValueError):
                overlay = 0
            overlay = max(0, min(1, overlay))
            if overlay:
                overlay_image = Image.new("RGBA", background_image.size, background)
                background_image = Image.blend(background_image, overlay_image, overlay)
            background_photo = ImageTk.PhotoImage(background_image)
            self._preview_photos.append(background_photo)
            tk.Label(
                stage,
                image=background_photo,
                bg=background,
                borderwidth=0,
            ).place(x=0, y=0, relwidth=1, relheight=1)

        if bool(self._value("show_header", False)):
            tk.Label(
                stage,
                text=self._value("header_text", "LR Remote Access"),
                bg=secondary,
                fg="#ffffff",
                anchor=tk.W,
                padx=12,
                pady=8,
                font=("Segoe UI", 9, "bold"),
            ).pack(fill=tk.X)

        card_width = 270
        try:
            configured_width = int(float(self._value("login_card_width", 420)))
            card_width = max(220, min(320, int(configured_width * 0.68)))
        except (TypeError, ValueError):
            pass
        position = str(self._value("login_card_position", "center"))
        anchor_map: dict[str, typing.Literal["center", "w", "e"]] = {
            "left": "w",
            "center": "center",
            "right": "e",
        }
        relx_map: dict[str, float] = {
            "left": 0.08,
            "center": 0.5,
            "right": 0.92,
        }
        anchor = anchor_map.get(position, "center")
        relx = relx_map.get(position, 0.5)
        card = tk.Frame(
            stage,
            bg=SURFACE,
            width=card_width,
            height=340,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.place(relx=relx, rely=0.49, anchor=anchor, width=card_width)

        if bool(self._value("show_logo", True)):
            if self._preview_assets.get("logo_url"):
                logo = self._preview_assets["logo_url"].copy()
                logo.thumbnail((card_width - 42, 46), Image.Resampling.LANCZOS)
                logo_photo = ImageTk.PhotoImage(logo)
                self._preview_photos.append(logo_photo)
                tk.Label(card, image=logo_photo, bg=SURFACE).pack(pady=(16, 5))
            else:
                tk.Label(
                    card,
                    text="LR",
                    bg=SURFACE,
                    fg=primary,
                    font=("Segoe UI", 14, "bold"),
                ).pack(pady=(16, 5))
        if bool(self._value("show_welcome_text", True)):
            tk.Label(
                card,
                text=self._value("welcome_heading", "Welcome"),
                bg=SURFACE,
                fg=secondary,
                wraplength=card_width - 30,
                font=("Segoe UI", 11, "bold"),
            ).pack(padx=12, pady=(5, 2))
            tk.Label(
                card,
                text=self._value("welcome_description", "Sign in to continue."),
                bg=SURFACE,
                fg=MUTED,
                wraplength=card_width - 30,
                font=("Segoe UI", 8),
            ).pack(padx=12, pady=(0, 10))
        if bool(self._value("show_company_code", True)):
            self._preview_input(card, "Company Code")
        self._preview_input(
            card,
            self._value("username_label", "Username"),
        )
        self._preview_input(
            card,
            self._value("password_label", "Password"),
        )
        if bool(self._value("show_remember_me", True)):
            tk.Label(
                card,
                text="☐  Remember Me",
                bg=SURFACE,
                fg=MUTED,
                font=("Segoe UI", 8),
            ).pack(anchor=tk.W, padx=16, pady=(2, 5))
        tk.Label(
            card,
            text=self._value("login_button_text", "Login"),
            bg=primary,
            fg="#ffffff",
            pady=7,
            font=("Segoe UI", 9, "bold"),
        ).pack(fill=tk.X, padx=16, pady=(3, 14))

        if bool(self._value("show_footer", True)):
            tk.Label(
                stage,
                text=self._value("footer_text", self._value("copyright_text", "")),
                bg=background,
                fg=MUTED,
                font=("Segoe UI", 7),
            ).pack(side=tk.BOTTOM, pady=8)

    @staticmethod
    def _preview_input(parent, label):
        tk.Label(
            parent,
            text=label,
            bg="#f4f7f5",
            fg=MUTED,
            anchor=tk.W,
            padx=9,
            pady=6,
            font=("Segoe UI", 8),
        ).pack(fill=tk.X, padx=16, pady=3)

    def _field_changed(self, *_args):
        if self._loading:
            return
        self._dirty = True
        self._update_state_label()
        self.after_idle(self._render_preview)

    def _pick_color(self, field):
        initial = self._value(field, "#159a35")
        selected = colorchooser.askcolor(initialcolor=initial, parent=self)[1]
        if selected:
            self.vars[field].set(selected.lower())

    def _update_state_label(self):
        version = int(self._settings.get("version") or 0)
        text = f"Draft v{version}"
        if self._dirty:
            text += "  •  Unsaved changes"
        self.state_label.configure(
            text=text,
            fg=DANGER if self._dirty else MUTED,
        )

    def _apply_settings(self, settings):
        settings = settings or {}
        config = settings.get("config") or {}
        self._loading = True
        try:
            for field, variable in self.vars.items():
                value = config.get(field)
                if isinstance(variable, tk.BooleanVar):
                    variable.set(bool(value))
                else:
                    variable.set("" if value is None else str(value))
        finally:
            self._loading = False
        self._settings = dict(settings)
        self._settings.update({
            "logo_url": config.get("logo_url"),
            "favicon_url": config.get("favicon_url"),
            "background_image_url": config.get("background_image_url"),
        })
        self._load_preview_assets(config)
        self.asset_labels["logo"].configure(
            text="Uploaded" if config.get("logo_url") else "No logo uploaded"
        )
        self.asset_labels["favicon"].configure(
            text="Uploaded" if config.get("favicon_url") else "No favicon uploaded"
        )
        self.asset_labels["background"].configure(
            text="Uploaded" if config.get("background_image_url") else "No background uploaded"
        )
        self._dirty = False
        self._update_state_label()
        self._render_preview()

    def _config_payload(self):
        return {
            field: variable.get()
            for field, variable in self.vars.items()
        }

    def _load_preview_assets(self, config):
        for field in ("logo_url", "favicon_url", "background_image_url"):
            url = config.get(field)
            if not url:
                self._asset_urls.pop(field, None)
                self._preview_assets.pop(field, None)
                continue
            if self._asset_urls.get(field) == url and field in self._preview_assets:
                continue
            try:
                content = self.app.client.portal_customization_asset(url)
                image = Image.open(io.BytesIO(content))
                image.load()
                self._preview_assets[field] = image.convert("RGBA")
                self._asset_urls[field] = url
            except (ApiError, OSError, ValueError):
                self._preview_assets.pop(field, None)
                self._asset_urls.pop(field, None)

    @staticmethod
    def _validate_payload(payload):
        text_limits = {
            "company_name": 120,
            "portal_title": 120,
            "browser_title": 120,
            "welcome_heading": 160,
            "welcome_description": 600,
            "username_label": 60,
            "password_label": 60,
            "login_button_text": 60,
            "header_text": 300,
            "footer_text": 600,
            "copyright_text": 300,
        }
        for field, limit in text_limits.items():
            value = str(payload.get(field) or "")
            if len(value) > limit:
                raise ValueError(
                    f"{field.replace('_', ' ').title()} must be at most {limit} characters."
                )
            if any(character in value for character in ("<", ">", "\x00")):
                raise ValueError(
                    f"{field.replace('_', ' ').title()} contains unsupported characters."
                )
        for field in (
            "primary_color",
            "secondary_color",
            "accent_color",
            "background_color",
        ):
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(payload.get(field) or "")):
                raise ValueError(f"{field.replace('_', ' ').title()} must be a 6-digit hex colour.")
        for field in ("support_url", "privacy_url", "terms_url"):
            value = str(payload.get(field) or "").strip()
            if value:
                parsed = urlparse(value)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    raise ValueError(f"{field.replace('_', ' ').title()} must use HTTP or HTTPS.")
        email = str(payload.get("support_email") or "").strip()
        if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValueError("Support Email is invalid.")
        ranges = {
            "background_overlay_opacity": (0.0, 1.0),
            "login_card_opacity": (0.3, 1.0),
            "login_card_width": (280.0, 720.0),
            "login_card_border_radius": (0.0, 48.0),
        }
        for field, (minimum, maximum) in ranges.items():
            try:
                number = float(payload.get(field))
            except (TypeError, ValueError) as error:
                raise ValueError(f"{field.replace('_', ' ').title()} must be a number.") from error
            if number < minimum or number > maximum:
                raise ValueError(
                    f"{field.replace('_', ' ').title()} must be between {minimum:g} and {maximum:g}."
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
                response = self.app.client.portal_customization_draft()
                self.after(0, lambda: self._on_refreshed(response, None))
            except Exception as error:
                self.after(0, lambda: self._on_refreshed(None, error))

        threading.Thread(target=worker, daemon=True).start()

    def _on_refreshed(self, response, error):
        self._is_loading = False
        if error:
            messagebox.showerror("Web Portal", str(error))
            self.app.set_status(f"Web Portal error: {error}")
            return
        self._apply_settings((response or {}).get("settings") or {})
        published = (response or {}).get("published")
        if published:
            self.state_label.configure(
                text=(
                    f"Draft v{self._settings.get('version', 0)}"
                    f"  •  Published v{published.get('version', 0)}"
                ),
                fg=MUTED,
            )
        self.app.set_status("Web Portal customization loaded")

    def _save_draft(self, *, show_message):
        if not self.app.require_login():
            return False
        try:
            payload = self._config_payload()
            self._validate_payload(payload)
            response = self.app.client.save_portal_customization_draft(
                payload
            )
            self._apply_settings(response.get("settings") or {})
            self.app.set_status("Web Portal draft saved")
            if show_message:
                messagebox.showinfo("Web Portal", "Draft saved. The public portal was not changed.")
            return True
        except (ApiError, ValueError) as error:
            messagebox.showerror("Web Portal", str(error))
            return False

    def save_draft(self):
        self._save_draft(show_message=True)

    def publish(self):
        if not self.app.require_login():
            return
        if not messagebox.askyesno(
            "Publish Web Portal",
            "Publish the saved portal customization to the public browser login page?",
        ):
            return
        if self._dirty and not self._save_draft(show_message=False):
            return
        try:
            response = self.app.client.publish_portal_customization()
            self.app.set_status("Web Portal customization published")
            messagebox.showinfo(
                "Web Portal",
                response.get("message") or "Portal customization published.",
            )
            self.refresh()
        except ApiError as error:
            messagebox.showerror("Web Portal", str(error))

    def reset_to_default(self):
        if not self.app.require_login():
            return
        if not messagebox.askyesno(
            "Reset Web Portal Draft",
            "Reset the draft to LR defaults? Published settings will remain live until you publish again.",
        ):
            return
        try:
            response = self.app.client.reset_portal_customization()
            self._apply_settings(response.get("settings") or {})
            self.app.set_status("Web Portal draft reset")
            messagebox.showinfo(
                "Web Portal",
                response.get("message") or "Draft reset to defaults.",
            )
        except ApiError as error:
            messagebox.showerror("Web Portal", str(error))

    def upload_asset(self, asset_type):
        if not self.app.require_login():
            return
        file_types = (
            [("Favicon", "*.png *.ico")]
            if asset_type == "favicon"
            else [("Images", "*.png *.jpg *.jpeg *.webp")]
        )
        path = filedialog.askopenfilename(
            parent=self,
            title=f"Select {asset_type.title()}",
            filetypes=file_types + [("All files", "*.*")],
        )
        if not path:
            return
        try:
            response = self.app.client.upload_portal_customization_asset(
                asset_type,
                path,
            )
            self._apply_settings(response.get("settings") or {})
            self.app.set_status(f"Web Portal {asset_type} uploaded")
            messagebox.showinfo(
                "Web Portal",
                response.get("message") or f"{asset_type.title()} uploaded.",
            )
        except (ApiError, OSError) as error:
            messagebox.showerror("Web Portal", str(error))
