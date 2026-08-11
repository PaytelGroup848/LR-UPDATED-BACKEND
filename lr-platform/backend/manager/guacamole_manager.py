import requests
import logging
import uuid
import ntpath
import re
import threading
import time
from requests.adapters import HTTPAdapter
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _unique_connection_name(name: str) -> str:
    base_name = str(name or "LR Remote Session").strip() or "LR Remote Session"
    suffix = uuid.uuid4().hex[:8]
    max_base_length = 128 - len(suffix) - 3
    return f"{base_name[:max_base_length]} - {suffix}"


def _working_directory(program: str | None, configured_directory: str | None = None) -> str:
    value = str(configured_directory or "").strip()
    if value and not value.lower().endswith((".exe", ".bat", ".cmd", ".msi")):
        return value

    program = str(program or "").strip()
    if "\\" in program:
        return ntpath.dirname(program)
    return ""


def _username_leaf(username: str | None) -> str:
    value = str(username or "").strip()
    if "\\" in value:
        value = value.rsplit("\\", 1)[-1]
    if "@" in value:
        value = value.split("@", 1)[0]
    return value


def _safe_app_name(value: str | None) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', " ", str(value or "").strip()).strip()
    return re.sub(r"\s+", " ", name) or "Application"


def _published_program_path(app: dict | None, program: str | None, username: str | None) -> str:
    program = str(program or "").strip()
    if not program:
        return program

    normalized = program.replace("/", "\\")
    match = re.match(r"^C:\\Users\\([^\\]+)\\", normalized, flags=re.IGNORECASE)
    if not match:
        return program

    if match.group(1).lower() == _username_leaf(username).lower():
        return program

    return ntpath.join(
        r"C:\ProgramData\LRPlatform\PublishedApps",
        _safe_app_name((app or {}).get("name")),
        ntpath.basename(normalized),
    )


def _folder_program(app: dict | None, program: str | None) -> str:
    folder_path = str((app or {}).get("folder_path") or "").strip()
    if not folder_path:
        return str(program or "").strip()
    return f'explorer.exe "{folder_path}"'


def _warn_if_likely_https_to_http_mismatch(public_url: str) -> None:
    parsed = urlparse(public_url or "")
    if parsed.scheme == "https" and parsed.port == 8080:
        logger.warning(
            "GUACAMOLE_PUBLIC_URL uses https on port 8080. The compose Guacamole "
            "service exposes plain HTTP on 8080; use http://...:8080/guacamole "
            "unless a TLS reverse proxy is terminating HTTPS."
        )


def _visual_parameters(profile: str) -> dict[str, str]:
    quality = str(profile or "balanced").strip().lower()

    if quality == "performance":
        return {
            "color-depth": "16",
            "enable-wallpaper": "false",
            "enable-theming": "false",
            "enable-font-smoothing": "false",
            "enable-full-window-drag": "false",
            "enable-desktop-composition": "false",
            "enable-menu-animations": "false",
            "disable-bitmap-caching": "false",
            "disable-offscreen-caching": "false",
            "disable-glyph-caching": "false",
        }

    if quality == "balanced":
        return {
            "color-depth": "24",
            "enable-wallpaper": "false",
            "enable-theming": "true",
            "enable-font-smoothing": "true",
            "enable-full-window-drag": "true",
            "enable-desktop-composition": "true",
            "enable-menu-animations": "false",
            "disable-bitmap-caching": "false",
            "disable-offscreen-caching": "false",
            "disable-glyph-caching": "false",
        }

    # Guacamole's RDP implementation supports at most 24-bit color. Keep the
    # high/ultra aliases for existing deployments without sending invalid 32-bit
    # connection parameters.
    return {
        "color-depth": "24",
        "enable-wallpaper": "true",
        "enable-theming": "true",
        "enable-font-smoothing": "true",
        "enable-full-window-drag": "true",
        "enable-desktop-composition": "true",
        "enable-menu-animations": "true",
        "disable-bitmap-caching": "false",
        "disable-offscreen-caching": "false",
        "disable-glyph-caching": "false",
    }
def _launch_mode(app: dict | None) -> str:
        if not app:
            return "remote_app"
        if (str(app.get("remote_app_program") or "").strip()):
            return "remote_app"
        if (str((app.get("initial_program") or app.get("target") or "")).strip()):
            return "initial_program"
        launch_mode = str(app.get("launch_mode") or "").strip()
        if launch_mode and launch_mode != "desktop":
            return launch_mode
        return "remote_app"


class GuacamoleClient:
    """
    Talks to the Guacamole REST API.

    Configure GUACAMOLE_URL, GUACAMOLE_USER, and GUACAMOLE_PASSWORD in .env.
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        public_url: str | None = None,
        data_source: str = "default",
        token_cache_seconds: int = 300,
        connect_timeout_seconds: float = 3.0,
        read_timeout_seconds: float = 10.0,
        visual_quality: str = 'balanced',
        enable_printing: bool = True,
        printer_name: str = "LR Remote Printer",
        max_connections: int = 1,
        max_connections_per_user: int = 1,
        http_client=None,
    ):
        self.base_url = base_url.rstrip("/")
        self.public_url = (public_url or base_url).rstrip("/")
        _warn_if_likely_https_to_http_mismatch(self.public_url)
        self.username = username
        self.password = password
        self.data_source = data_source or "default"
        self._token = None
        self._token_expires_at = 0.0
        self._token_cache_seconds = max(5, int(token_cache_seconds))
        self._token_lock = threading.Lock()
        self._timeout = (max(0.1, float(connect_timeout_seconds)), max(0.1, float(read_timeout_seconds)))
        self.visual_quality = str(visual_quality or 'balanced').strip().lower()
        self.enable_printing = bool(enable_printing)
        self.printer_name = str(printer_name or "LR Remote Printer").strip()[:128]
        self.max_connections = max(1, int(max_connections))
        self.max_connections_per_user = max(1, int(max_connections_per_user))
        self._http = http_client or requests


    


    def _get_admin_token(self, force: bool = False) -> str | None:
        now = time.monotonic()
        if not force and self._token and now < self._token_expires_at:
            return self._token
        with self._token_lock:
            now = time.monotonic()
            if not force and self._token and now < self._token_expires_at:
                return self._token
            return self._authenticate_admin(now)

    def _authenticate_admin(self, now: float) -> str | None:
        """Authenticate as admin and return token."""
        self._token = None
        self._token_expires_at = 0.0
        try:
            logger.info("Authenticating with Guacamole at %s as %s", self.base_url, self.username)
            resp = self._http.post(
                f"{self.base_url}/api/tokens",
                data={"username": self.username, "password": self.password},
                timeout=self._timeout,
            )
            if resp.status_code == 200:
                self._token_expires_at = now + self._token_cache_seconds
                self._token = resp.json().get("authToken")
                return self._token
            logger.error(f"Guacamole admin auth failed: {resp.status_code} {resp.text}")
            return None
        except Exception as e:
            logger.error(f"Guacamole connection error: {e}")
            return None

    def _headers(self) -> dict:
        return {"Content-Type": "application/json"}

    def _params(self) -> dict:
        if not self._token:
            self._get_admin_token()
        return {"token": self._token}

    def get_admin_token(self) -> str | None:
        """Return a bounded cached Guacamole token for browser client URLs."""
        return self._get_admin_token()

    # ── public API ───────────────────────────────────────────────────────────

    def get_user_token(self, username: str, password: str) -> dict:
        """
        Authenticate an end-user against Guacamole and get their auth token.
        Returns {"success": True, "token": "...", "data_source": "..."}
        """
        try:
            resp = self._http.post(
                f"{self.base_url}/api/tokens",
                data={"username": username, "password": password},
                timeout=self._timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "success":     True,
                    "token":       data.get("authToken"),
                    "data_source": data.get("dataSource"),
                    "username":    data.get("username"),
                }
            return {"success": False, "error": f"Auth failed: {resp.status_code}"}
        except Exception as e:
            logger.error(f"Guacamole get_user_token error: {e}")
            return {"success": False, "error": str(e)}

    def create_rdp_connection(
        self,
        name: str,
        host: str,
        port: int = 3389,
        rdp_username: str = "",
        rdp_password: str = "",
        domain: str = "",
        security: str = "any",
        ignore_cert: bool = True,
        app: dict | None = None,
        require_remote_app: bool = False,
    ) -> dict:
        """
        Create a new RDP connection in Guacamole.
        Returns {"success": True, "connection_id": "..."}
        """
        token = self._get_admin_token()
        if not token:
            return {"success": False, "error": "Could not authenticate to Guacamole"}

        host = self._normalize_rdp_host(host)
        logger.info("Creating Guacamole RDP connection host=%s port=%s user=%s app=%s", host, port, rdp_username, app)

        parameters = {
            "hostname":          host,
            "port":              str(port),
            "username":          rdp_username,
            "password":          rdp_password,
            "domain":            domain,
            "security":          security,
            "ignore-cert":       "true" if ignore_cert else "false",
            "enable-drive":         "true",
            "drive-name":           "Web Storage",
            "drive-path":           "/tmp",
            "create-drive-path":    "true",
            "disable-download":     "false",
            "disable-upload":       "false",
            "enable-printing":   str(self.enable_printing).lower(),
            "printer-name":      self.printer_name,
            "resize-method":     "display-update",
            # Guacamole 1.6 enables the RDP Graphics Pipeline by default. Keep
            # this explicit so generated connections cannot inherit an old
            # disable-gfx value, and allow Guacamole to use lossy updates for
            # high-motion content instead of forcing bandwidth-heavy PNGs.
            "disable-gfx":       "false",
            "force-lossless":    "false",
            "disable-audio":     "false",
            "disable-copy":      "false",
            "disable-paste":     "false",
            **_visual_parameters(self.visual_quality),
        }

        if app:
            display_mode = app.get("display_mode") or "remote_app"
            launch_mode = "desktop" if display_mode == "full_desktop" else _launch_mode(app)
            # Only the dedicated RemoteApp handler enables RAIL parameters.
            # Other HTML5/desktop callers keep their existing initial-program flow.
            remote_app_program = (
                (app.get("remote_app_program") or "").strip()
                if require_remote_app
                else ""
            )
            initial_program = (app.get("initial_program") or app.get("target") or "").strip()

            if launch_mode == "remote_app" and remote_app_program:
                # Guacamole's RDP protocol expects the published program itself
                # in `remote-app` (for example, "||notepad").  The
                # `remote-app-program`/`remote-app-name` keys are .rdp-file
                # concepts and are ignored by guacd.
                parameters["remote-app"] = remote_app_program

                if app.get("working_directory"):
                    parameters["remote-app-dir"] = app["working_directory"]
                if app.get("arguments"):
                    parameters["remote-app-args"] = app["arguments"]

            elif launch_mode == "initial_program" and initial_program:
                initial_program = _published_program_path(app, initial_program, rdp_username)
                initial_program = _folder_program(app, initial_program)
                parameters["initial-program"] = initial_program
                working_directory = _working_directory(initial_program, app.get("working_directory"))
                if working_directory:
                    parameters["remote-app-dir"] = working_directory
                if app.get("arguments"):
                    parameters["remote-app-args"] = app["arguments"]

            elif require_remote_app:
                return {"success": False, "error": "RemoteApp program is required"}

        payload = {
            "name":           _unique_connection_name(name),
            "protocol":       "rdp",
            "parentIdentifier": "ROOT",
            "parameters": parameters,
            "attributes": {
                "max-connections": str(self.max_connections),
                "max-connections-per-user": str(self.max_connections_per_user),
            }
        }

        try:
            resp = self._http.post(
                f"{self.base_url}/api/session/data/{self._data_source()}/connections",
                json=payload,
                params={"token": token},
                timeout=self._timeout,
            )
            if resp.status_code == 401:
                token = self._get_admin_token(force=True)
                if token:
                    resp = self._http.post(
                        f"{self.base_url}/api/session/data/{self._data_source()}/connections",
                        json=payload,
                        params={"token": token},
                        timeout=self._timeout,
                    )

            if resp.status_code in (200, 201):
                data = resp.json()
                connection_id = data.get("identifier")
                return {
                    "success": True,
                    "connection_id": connection_id,
                    "token": token,
                    "data_source": self._data_source(),
                    "client_url": self.build_client_url(connection_id, token),
                }
            return {"success": False, "error": f"{resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Guacamole create_rdp_connection error: {e}")
            return {"success": False, "error": str(e)}

    def delete_connection(self, connection_id: str) -> dict:
        """Delete a Guacamole connection."""
        token = self._get_admin_token()
        if not token:
            return {"success": False, "error": "Could not authenticate to Guacamole"}
        try:
            resp = self._http.delete(
                f"{self.base_url}/api/session/data/{self._data_source()}/connections/{connection_id}",
                params={"token": token},
                timeout=self._timeout,
            )
            return {"success": resp.status_code in (200, 204)}
        except Exception as e:
            logger.error(f"Guacamole delete_connection error: {e}")
            return {"success": False, "error": str(e)}

    def list_active_connections(self) -> dict:
        """List all currently active Guacamole connections."""
        token = self._get_admin_token()
        if not token:
            return {"success": False, "error": "Could not authenticate to Guacamole"}
        try:
            resp = self._http.get(
                f"{self.base_url}/api/session/data/{self._data_source()}/activeConnections",
                params={"token": token},
                timeout=self._timeout,
            )
            if resp.status_code == 200:
                return {"success": True, "connections": resp.json()}
            return {"success": False, "error": f"{resp.status_code}: {resp.text}"}
        except Exception as e:
            logger.error(f"Guacamole list_active_connections error: {e}")
            return {"success": False, "error": str(e)}

    def kill_connection(self, active_connection_id: str) -> dict:
        """Kill a specific active connection by its active connection ID."""
        token = self._get_admin_token()
        if not token:
            return {"success": False, "error": "Could not authenticate to Guacamole"}
        try:
            resp = self._http.patch(
                f"{self.base_url}/api/session/data/{self._data_source()}/activeConnections",
                json=[{"op": "remove", "path": f"/{active_connection_id}"}],
                params={"token": token},
                timeout=self._timeout,
            )
            return {"success": resp.status_code in (200, 204)}
        except Exception as e:
            logger.error(f"Guacamole kill_connection error: {e}")
            return {"success": False, "error": str(e)}

    def build_client_url(self, connection_id: str, token: str, data_source: str | None = None) -> str:
        """
        Build the URL the browser opens to show the RDP desktop.
        Format: /guacamole/#/client/<b64_connection_id>?token=<user_token>
        """
        import base64
        source = data_source or self._data_source()
        encoded = base64.b64encode(
            f"{connection_id}\x00c\x00{source}".encode()
        ).decode()
        return f"{self.public_url}/#/client/{encoded}?token={token}"

    def _data_source(self) -> str:
        return self.data_source

    def _normalize_rdp_host(self, host: str) -> str:
        host = (host or "").strip()
        if host.lower() in ("localhost", "127.0.0.1", "::1"):
            return "host.docker.internal"
        return host


# ── singleton factory (import this in routes) ────────────────────────────────

_client_lock = threading.Lock()
_client_key = None
_client_instance = None


def get_guac_client() -> GuacamoleClient:
    from flask import current_app
    global _client_key, _client_instance
    key = (current_app.config["GUACAMOLE_URL"], current_app.config["GUACAMOLE_USER"],
           current_app.config["GUACAMOLE_PASSWORD"], current_app.config.get("GUACAMOLE_PUBLIC_URL"),
           current_app.config.get("GUACAMOLE_DATA_SOURCE", "default"),
           current_app.config.get("GUACAMOLE_VISUAL_QUALITY", "balanced"),
           current_app.config.get("GUACAMOLE_ENABLE_PRINTING", True),
           current_app.config.get("GUACAMOLE_PRINTER_NAME", "LR Remote Printer"))
    if _client_instance is not None and key == _client_key:
        return _client_instance
    return _new_guac_client(current_app, key)


def _new_guac_client(app, key) -> GuacamoleClient:
    global _client_key, _client_instance
    with _client_lock:
        if _client_instance is not None and key == _client_key:
            return _client_instance
        pool_size = max(4, int(app.config.get("GUACAMOLE_HTTP_POOL_SIZE", 100)))
        session = requests.Session()
        adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        _client_instance = GuacamoleClient(
            base_url=key[0], username=key[1], password=key[2],
            public_url=key[3], data_source=key[4],
            token_cache_seconds=app.config.get("GUACAMOLE_TOKEN_CACHE_SECONDS", 300),
            connect_timeout_seconds=app.config.get("GUACAMOLE_CONNECT_TIMEOUT_SECONDS", 3.0),
            read_timeout_seconds=app.config.get("GUACAMOLE_READ_TIMEOUT_SECONDS", 10.0),
            visual_quality=key[5],
            enable_printing=key[6],
            printer_name=key[7],
            max_connections=app.config.get("GUACAMOLE_MAX_CONNECTIONS", 1),
            max_connections_per_user=app.config.get("GUACAMOLE_MAX_CONNECTIONS_PER_USER", 1),
            http_client=session,
        )
        _client_key = key
        return _client_instance
