import os
import ntpath
import re
import socket
import hashlib
import hmac
from datetime import datetime, timedelta
from secrets import token_urlsafe
from urllib.parse import quote

from bson.objectid import ObjectId
from flask import current_app, has_app_context, has_request_context, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from backend.models.application import PublishedApp
from backend.models.assignment import ApplicationAssignment
from backend.models.rdp_session import RdpSession
from backend.models.server import Server
from backend.models.user import User
from backend.security.credential_crypto import decrypt_secret
from backend.services.access_policy_service import AccessPolicyService
from backend.services.audit_service import AuditService


_BROWSER_REMOTE_APP_TICKET_SALT = "lr-browser-remote-app-v1"


def _object_id(value):
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return None


def _id_variants(value) -> list[object]:
    variants: list[object] = [str(value)]
    object_id = _object_id(value)
    if object_id:
        variants.append(object_id)
    return variants


def _session_response(session):
    data = RdpSession.to_dict(session)

    if session.get("server_id"):
        server = Server.get_by_id(session.get("server_id"))
        if server:
            data["server_name"] = server.get("name")

    app_name = data.get("published_app_name")
    if app_name:
        data["app_name"] = app_name
        data["application_name"] = app_name

    return data


def _guacamole_configured():
    return all(
        current_app.config.get(key)
        for key in ("GUACAMOLE_URL", "GUACAMOLE_USER", "GUACAMOLE_PASSWORD")
    )


def _rdp_line(key, value):
    return f"{key}:s:{str(value or '').replace(chr(10), ' ').replace(chr(13), ' ')}"


def _rdp_int_line(key, value):
    return f"{key}:i:{int(value)}"


def _normalize_remote_app_alias(alias):
    alias = str(alias or "").strip()
    if alias.startswith("||"):
        alias = alias[2:]
    alias = re.sub(r"[^a-zA-Z0-9_-]+", "-", alias).strip("-_")
    return alias.lower()


def _native_remote_app_rdp_lines(app):
    remote_app_program = str((app or {}).get("remote_app_program") or "").strip()
    remote_app_alias = str((app or {}).get("remote_app_alias") or "").strip()

    if remote_app_program.startswith("||"):
        remote_app_program = f"||{_normalize_remote_app_alias(remote_app_program)}"
    elif remote_app_program and "\\" not in remote_app_program and "/" not in remote_app_program:
        remote_app_program = f"||{_normalize_remote_app_alias(remote_app_program)}"
    elif remote_app_alias:
        remote_app_program = f"||{_normalize_remote_app_alias(remote_app_alias)}"

    if not remote_app_program or not remote_app_program.startswith("||"):
        return []

    lines = [
        _rdp_int_line("remoteapplicationmode", 1),
        _rdp_line("remoteapplicationprogram", remote_app_program),
        _rdp_line("remoteapplicationname", (app or {}).get("remote_app_alias") or (app or {}).get("name")),
        _rdp_line("remoteapplicationcmdline", (app or {}).get("arguments")),
    ]
    working_directory = str((app or {}).get("working_directory") or (app or {}).get("folder_path") or "").strip()
    if working_directory:
        lines.append(_rdp_line("shell working directory", working_directory))
    return lines


def _native_rdp_precheck(host, port):
    if not has_app_context():
        return None
    configured = current_app.config.get("RDP_PRECHECK_ENABLED", "true")
    enabled = (
        configured
        if isinstance(configured, bool)
        else str(configured or "").strip().lower() not in {"0", "false", "no", "off"}
    )
    if not enabled:
        return None
    timeout = float(current_app.config.get("RDP_PRECHECK_TIMEOUT", 3) or 3)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return None
    except OSError:
        return "Assigned RDP server is unavailable"


def _external_base_url():
    forwarded_host = request.headers.get("X-Forwarded-Host")
    forwarded_proto = request.headers.get("X-Forwarded-Proto") or request.scheme
    if forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}".rstrip("/")
    return request.host_url.rstrip("/")


def _browser_launch_ttl_seconds():
    if not has_app_context():
        return 120
    try:
        return max(30, min(int(current_app.config.get("REMOTEAPP_BROWSER_LAUNCH_TTL_SECONDS", 120)), 600))
    except (TypeError, ValueError):
        return 120


def _browser_launch_serializer():
    return URLSafeTimedSerializer(
        current_app.secret_key,
        salt=_BROWSER_REMOTE_APP_TICKET_SALT,
    )


def _browser_launch_ticket(session, user, app, server):
    nonce = token_urlsafe(24)
    payload = {
        "sid": str(session.get("_id")),
        "uid": str((user or {}).get("_id") or (user or {}).get("id") or ""),
        "tid": str((user or {}).get("tenant_id") or ""),
        "aid": str((app or {}).get("_id") or ""),
        "rid": str((server or {}).get("_id") or ""),
        "nonce": nonce,
    }
    return (
        _browser_launch_serializer().dumps(payload),
        hashlib.sha256(nonce.encode("utf-8")).hexdigest(),
    )


def _display_mode(app):
    if not app:
        return "full_desktop"
    return app.get("display_mode") or (
        "full_desktop" if app.get("launch_mode") == "desktop" else "remote_app"
    )


def _launch_mode(app, display_mode):
    if not app or display_mode == "full_desktop":
        return "desktop"
    if (app.get("remote_app_program") or "").strip():
        return "remote_app"
    if (app.get("initial_program") or app.get("target") or "").strip():
        return "initial_program"
    launch_mode = app.get("launch_mode")
    if launch_mode and launch_mode != "desktop":
        return launch_mode
    return "remote_app"


def _requested_view(data):
    value = str((data or {}).get("view_mode") or (data or {}).get("display_mode") or "").strip().lower()
    if value in {"desktop", "full_desktop", "remote_desktop"}:
        return "full_desktop"
    if value in {"app", "remote_app", "remoteapp", "published_app"}:
        return "remote_app"
    if value in {"web", "web_view", "html5", "browser"}:
        return "html5"
    return None


def _force_html5_gateway(data):
    value = (data or {}).get("force_html5_gateway") or (data or {}).get("use_html5_gateway")
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _ignore_stored_display_mode(data):
    value = (data or {}).get("ignore_stored_display_mode")
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _rdp_identity_for_user(user, server):
    portal_username = (user or {}).get("username") or ""
    windows_username = (user or {}).get("windows_username") or portal_username
    windows_password = decrypt_secret((user or {}).get("windows_password"))
    account_scope = str((user or {}).get("windows_account_scope") or "").strip().lower()
    if account_scope == "local":
        windows_domain = ""
        if windows_username and "\\" not in windows_username and "@" not in windows_username:
            windows_username = f".\\{windows_username}"
    else:
        windows_domain = (
            (user or {}).get("windows_domain")
            or server.get("windows_domain")
            or server.get("domain")
            or server.get("hostname")
            or ""
        )

    if windows_username:
        return {
            "username": windows_username,
            "password": windows_password or "",
            "domain": windows_domain,
            "mode": "per_user_windows_account" if windows_password else "per_user_windows_username",
            "isolated": True,
            "warning": None if windows_password else (
                "Windows password is not stored for this user. The remote desktop client may ask once."
            ),
        }

    return {
        "username": server.get("username") or "",
        "password": decrypt_secret(server.get("password")),
        "domain": server.get("windows_domain") or server.get("domain") or server.get("hostname") or "",
        "mode": "shared_server_credentials",
        "isolated": False,
        "warning": (
            "This launch is using shared server credentials. "
            "Assign a Windows account to the LR user for isolated per-user sessions."
        ),
    }


def _local_windows_domain(username, domain):
    if domain or not username:
        return domain or ""
    if "\\" in username or "@" in username:
        return ""
    return "."


def _guacamole_windows_identity(username, domain, server):
    """Return separate username/domain values for FreeRDP/NLA."""
    username = str(username or "").strip()
    domain = str(domain or "").strip()
    if not username:
        return "", domain

    separator = chr(92)
    if separator in username:
        prefix, leaf = username.rsplit(separator, 1)
        if prefix == ".":
            local_machine = str(
                (server or {}).get("agent_hostname")
                or (server or {}).get("hostname")
                or "."
            ).strip()
            return leaf, domain or local_machine
        return leaf, domain or prefix

    if "@" in username:
        return username, domain
    return username, _local_windows_domain(username, domain)


def _rdp_login_name(username, domain):
    if not username:
        return ""
    if "\\" in username or "@" in username:
        return username
    if domain:
        return f"{domain}\\{username}"
    return f".\\{username}"


def _working_directory(program, configured_directory=None):
    value = str(configured_directory or "").strip()
    if value and not value.lower().endswith((".exe", ".bat", ".cmd", ".msi")):
        return value

    program = str(program or "").strip()
    if "\\" in program:
        return ntpath.dirname(program)
    return ""


def _username_leaf(username):
    value = str(username or "").strip()
    if "\\" in value:
        value = value.rsplit("\\", 1)[-1]
    if "@" in value:
        value = value.split("@", 1)[0]
    return value


def _safe_app_name(value):
    name = re.sub(r'[\\/:*?"<>|]+', " ", str(value or "").strip()).strip()
    return re.sub(r"\s+", " ", name) or "Application"


def _published_program_path(app, program, username):
    program = str(program or "").strip()
    if not program:
        return program

    normalized = program.replace("/", "\\")
    match = re.match(r"^C:\\Users\\([^\\]+)\\", normalized, flags=re.IGNORECASE)
    if not match:
        return program

    source_user = match.group(1).lower()
    target_user = _username_leaf(username).lower()
    if source_user == target_user:
        return program

    app_name = _safe_app_name((app or {}).get("name"))
    return ntpath.join(
        r"C:\ProgramData\LRPlatform\PublishedApps",
        app_name,
        ntpath.basename(normalized),
    )


def _folder_program(app, program):
    folder_path = str((app or {}).get("folder_path") or "").strip()
    if not folder_path:
        return program
    return f'explorer.exe "{folder_path}"'


def _session_query(user_id, server, app):
    query = {
        "user_id": {"$in": _id_variants(user_id)},
        "server_id": server.get("_id"),
        "status": {"$in": ["active", "pending"]},
    }
    if app:
        query["published_app_id"] = app.get("_id")
        query["display_mode"] = app.get("display_mode")
    else:
        query["published_app_id"] = None
    return query


class PortalService:

    @staticmethod
    def get_current_user(user):
        data = User.to_dict(user)
        data["is_admin"] = User.is_admin(user)
        return data

    @staticmethod
    def get_home_servers():
        return [Server.to_dict(server) for server in Server.find_active()]

    @staticmethod
    def get_dashboard_data():
        return {
            "stats": PortalService.get_session_stats(None)[0],
            "servers": PortalService.get_home_servers()
        }

    @staticmethod
    def get_portal_servers():
        return {
            "success": True,
            "servers": [Server.to_dict(server) for server in Server.find_active()]
        }, 200

    @staticmethod
    def get_portal_apps(user_id):
        apps = PublishedApp.assigned_to_user(user_id)
        return {
            "success": True,
            "apps": [PublishedApp.to_dict(app) for app in apps]
        }, 200

    @staticmethod
    def launch_app(app_id, user_id, ip_address, user_agent, data=None):
        requested_view = _requested_view(data)
        force_html5_gateway = _force_html5_gateway(data)
        ignore_stored_display_mode = _ignore_stored_display_mode(data)
        allowed, reason, app = AccessPolicyService.can_launch_app(user_id, app_id)
        if not allowed:
            AuditService.log(
                "session.launch_app.denied",
                user_id=user_id,
                category="session",
                ip_address=ip_address,
                success=False,
                reason=reason,
                metadata={"app_id": str(app_id)},
            )
            return {"success": False, "error": reason}, 403 if app else 404

        if app is None:
            return {"success": False, "error": "Application not found"}, 404

        server = Server.get_by_id(app.get("server_id"))
        if server is None:
            return {"success": False, "error": "Assigned server is not available"}, 404

        launch_data = PortalService._create_launch_session(
            user_id=user_id,
            server=server,
            app=app,
            ip_address=ip_address,
            user_agent=user_agent,
            requested_view=requested_view,
            force_html5_gateway=force_html5_gateway,
            ignore_stored_display_mode=ignore_stored_display_mode,
        )
        return launch_data

    @staticmethod
    def launch_remote_app(app_id, user_id, ip_address, user_agent):
        """Create one RemoteApp session for HTML5 browsers and native clients."""
        allowed, reason, app = AccessPolicyService.can_launch_app(user_id, app_id)
        if not allowed:
            return {"success": False, "error": reason}, 403 if app else 404

        item_type = str(app.get("item_type") or "").strip().lower()
        remote_app_program = str(app.get("remote_app_program") or "").strip()
        if item_type == "desktop":
            return {"success": False, "error": "Selected resource is not a published RemoteApp"}, 400
        if not remote_app_program:
            return {
                "success": False,
                "error": "RemoteApp configuration is incomplete.",
            }, 422

        server = Server.get_by_id(app.get("server_id"))
        if server is None or server.get("is_active") is False:
            return {"success": False, "error": "Assigned server is not available"}, 404
        host = str(server.get("host") or server.get("ip_address") or "").strip()
        if not host:
            return {"success": False, "error": "RemoteApp configuration is incomplete."}, 422
        try:
            port = int(server.get("port") or 3389)
        except (TypeError, ValueError):
            return {"success": False, "error": "RemoteApp configuration is incomplete."}, 422
        if not 1 <= port <= 65535:
            return {"success": False, "error": "RemoteApp configuration is incomplete."}, 422

        launch, status_code = PortalService._create_launch_session(
            user_id=user_id,
            server=server,
            app=app,
            ip_address=ip_address,
            user_agent=user_agent,
            requested_view="remote_app",
            force_html5_gateway=True,
            ignore_stored_display_mode=True,
            require_remote_app=True,
        )
        if status_code != 200 or not launch.get("success"):
            return launch, status_code

        session_id = str(launch.get("session_id") or "")
        session_object_id = _object_id(session_id)
        user = User.get_by_id(user_id)
        if not session_object_id or not user:
            return {"success": False, "error": "Unable to start the RemoteApp session."}, 500

        ticket, nonce_hash = _browser_launch_ticket(
            {"_id": session_object_id},
            user,
            app,
            server,
        )
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=_browser_launch_ttl_seconds())
        rdp_file_expires_at = now + timedelta(minutes=2)
        updated = RdpSession.collection.update_one(
            {"_id": session_object_id},
            {"$set": {
                "native_remote_app": True,
                "rdp_file_expires_at": rdp_file_expires_at,
                "rdp_file_downloaded_at": None,
                "browser_launch_nonce_hash": nonce_hash,
                "browser_launch_expires_at": expires_at,
                "browser_launch_used_at": None,
            }},
        )
        if updated.matched_count != 1:
            connection_id = launch.get("connection_id")
            if connection_id:
                try:
                    from backend.manager.guacamole_manager import get_guac_client

                    get_guac_client().delete_connection(str(connection_id))
                except Exception:
                    pass
            return {"success": False, "error": "Unable to start the RemoteApp session."}, 500

        browser_launch_url = (
            f"{_external_base_url()}/api/lr/sessions/{session_id}/open"
            f"?ticket={quote(ticket, safe='')}"
        )
        launch.update({
            "launch_transport": "html5_remoteapp",
            "launch_url": browser_launch_url,
            "rdp_file_url": f"/api/lr/sessions/{session_id}/file.rdp",
            "resource_id": str(app.get("_id")),
            "application_name": app.get("name") or "RemoteApp",
        })
        if isinstance(launch.get("session"), dict):
            launch["session"].update({
                "native_remote_app": True,
                "rdp_file_expires_at": rdp_file_expires_at.isoformat(),
            })
        return launch, 200

    @staticmethod
    def consume_browser_remote_app_launch(session_id, ticket, user):
        """Consume a signed, user-bound launch ticket and return the internal viewer URL."""
        if not ticket:
            return {"success": False, "error": "RemoteApp launch ticket is required."}, 401
        try:
            payload = _browser_launch_serializer().loads(
                ticket,
                max_age=_browser_launch_ttl_seconds(),
            )
        except SignatureExpired:
            return {"success": False, "error": "RemoteApp launch ticket has expired."}, 401
        except BadSignature:
            return {"success": False, "error": "RemoteApp launch ticket is invalid."}, 403

        allowed, reason, session = AccessPolicyService.can_view_session(user, session_id)
        if not allowed or not session:
            return {"success": False, "error": reason or "Session not found"}, 403 if session else 404

        user_id = str(getattr(user, "id", None) or user.get("_id") or "")
        tenant_id = str(user.get("tenant_id") or "")
        expected = {
            "sid": str(session.get("_id")),
            "uid": user_id,
            "tid": tenant_id,
            "aid": str(session.get("published_app_id") or ""),
            "rid": str(session.get("server_id") or ""),
        }
        if any(str(payload.get(key) or "") != value for key, value in expected.items()):
            return {"success": False, "error": "RemoteApp launch ticket is not valid for this session."}, 403

        expires_at = session.get("browser_launch_expires_at")
        if expires_at and expires_at < datetime.utcnow():
            return {"success": False, "error": "RemoteApp launch ticket has expired."}, 401
        nonce_hash = hashlib.sha256(str(payload.get("nonce") or "").encode("utf-8")).hexdigest()
        if not hmac.compare_digest(nonce_hash, str(session.get("browser_launch_nonce_hash") or "")):
            return {"success": False, "error": "RemoteApp launch ticket is invalid."}, 403

        consumed = RdpSession.collection.update_one(
            {
                "_id": session.get("_id"),
                "status": {"$in": ["active", "pending"]},
                "browser_launch_nonce_hash": nonce_hash,
                "$or": [
                    {"browser_launch_used_at": None},
                    {"browser_launch_used_at": {"$exists": False}},
                ],
            },
            {"$set": {"browser_launch_used_at": datetime.utcnow()}},
        )
        if consumed.matched_count != 1:
            return {"success": False, "error": "RemoteApp launch ticket has already been used."}, 409

        internal_url = session.get("launch_url")
        if not internal_url:
            return {"success": False, "error": "Unable to start the RemoteApp session."}, 502
        return {"success": True, "redirect_url": internal_url}, 200

    @staticmethod
    def launch_native_remote_app(app_id, user_id, ip_address, user_agent):
        """Launch an assigned app through the native Windows RDP RemoteApp client."""
        allowed, reason, app = AccessPolicyService.can_launch_app(user_id, app_id)
        if not allowed:
            status_code = 404 if not app or reason == "Assigned server is not available" else 403
            return {"success": False, "error": reason}, status_code

        item_type = str(app.get("item_type") or "").strip().lower()
        remote_app_program = str(app.get("remote_app_program") or "").strip()
        if item_type == "desktop":
            return {"success": False, "error": "Selected resource is not a published RemoteApp"}, 400
        if not remote_app_program:
            return {
                "success": False,
                "error": "Published application is missing its RemoteApp program",
            }, 400

        server = Server.get_by_id(app.get("server_id"))
        if server is None or server.get("is_active") is False:
            return {"success": False, "error": "Assigned server is not available"}, 404
        if not str(server.get("host") or server.get("ip_address") or "").strip():
            return {"success": False, "error": "Assigned server is missing its RDP address"}, 400
        try:
            port = int(server.get("port") or 3389)
        except (TypeError, ValueError):
            return {"success": False, "error": "Assigned server has an invalid RDP port"}, 400
        if not 1 <= port <= 65535:
            return {"success": False, "error": "Assigned server has an invalid RDP port"}, 400
        precheck_error = _native_rdp_precheck(
            str(server.get("host") or server.get("ip_address")).strip(),
            port,
        )
        if precheck_error:
            return {"success": False, "error": precheck_error}, 502

        return PortalService._create_launch_session(
            user_id=user_id,
            server=server,
            app=app,
            ip_address=ip_address,
            user_agent=user_agent,
            requested_view="remote_app",
            force_html5_gateway=False,
            ignore_stored_display_mode=True,
            native_remote_app=True,
        )

    @staticmethod
    def launch_native_desktop(server_id, user_id, ip_address, user_agent):
        """Launch a full assigned Windows desktop through the existing native RDP file flow."""
        user = User.get_by_id(user_id)
        allowed, reason, server = AccessPolicyService.can_launch_server(user, server_id)
        if not allowed:
            return {"success": False, "error": reason}, 403 if server else 404
        if server is None or server.get("is_active") is False:
            return {"success": False, "error": "Assigned server is not available"}, 404

        host = str(server.get("host") or server.get("ip_address") or "").strip()
        if not host:
            return {"success": False, "error": "Assigned server is missing its RDP address"}, 400
        try:
            port = int(server.get("port") or 3389)
        except (TypeError, ValueError):
            return {"success": False, "error": "Assigned server has an invalid RDP port"}, 400
        if not 1 <= port <= 65535:
            return {"success": False, "error": "Assigned server has an invalid RDP port"}, 400
        precheck_error = _native_rdp_precheck(host, port)
        if precheck_error:
            return {"success": False, "error": precheck_error}, 502

        return PortalService._create_launch_session(
            user_id=user_id,
            server=server,
            app=None,
            ip_address=ip_address,
            user_agent=user_agent,
            requested_view="full_desktop",
            force_html5_gateway=False,
            ignore_stored_display_mode=True,
        )

    @staticmethod
    def launch_server(data, user_id, ip_address, user_agent):
        server_id = data.get("server_id")
        requested_view = _requested_view(data)
        user = User.get_by_id(user_id)
        allowed, reason, server = AccessPolicyService.can_launch_server(user, server_id)
        if not allowed:
            AuditService.log(
                "session.launch_server.denied",
                user=user,
                user_id=user_id,
                category="session",
                server_id=server_id,
                ip_address=ip_address,
                success=False,
                reason=reason,
            )
            return {"success": False, "error": reason}, 403 if server else 404

        if server is None:
            return {"success": False, "error": "Server not found"}, 404

        return PortalService._create_launch_session(
            user_id=user_id,
            server=server,
            app=None,
            ip_address=ip_address,
            user_agent=user_agent,
            requested_view=requested_view,
        )

    @staticmethod
    def _create_launch_session(
        user_id,
        server,
        app,
        ip_address,
        user_agent,
        requested_view=None,
        force_html5_gateway=False,
        ignore_stored_display_mode=False,
        require_remote_app=False,
        native_remote_app=False,
    ):
        user = User.get_by_id(user_id)
        display_mode = requested_view or (None if ignore_stored_display_mode else _display_mode(app))
        display_mode = (display_mode or "remote_app") if app else (display_mode or "full_desktop")
        launch_mode = _launch_mode(app, display_mode)
        launch_app = dict(app, display_mode=display_mode, launch_mode=launch_mode) if app else None
        use_html5_gateway = force_html5_gateway or display_mode == "html5"

        rdp_identity = _rdp_identity_for_user(user, server)
        connection_id = None
        launch_url = None
        guac_token = None
        warning = rdp_identity.get("warning")

        if use_html5_gateway and _guacamole_configured():
            try:
                from backend.manager.guacamole_manager import get_guac_client

                client = get_guac_client()
                guac_username, guac_domain = _guacamole_windows_identity(
                    rdp_identity.get("username"),
                    rdp_identity.get("domain"),
                    server,
                )
                connection_name = str(
                    (launch_app.get("name") if launch_app else server.get("name"))
                    or "LR Remote Session"
                )
                if user and user.get("tenant_id"):
                    connection_name = f"tenant-{str(user.get('tenant_id'))[:12]}-{connection_name}"
                connection_host = str(server.get("host") or server.get("ip_address") or "")
                result = client.create_rdp_connection(
                    name=connection_name,
                    host=connection_host,
                    port=int(server.get("port") or 3389),
                    rdp_username=guac_username,
                    rdp_password=rdp_identity.get("password") or "",
                    domain=guac_domain,
                    app=launch_app,
                    require_remote_app=require_remote_app,
                )
                if result.get("success"):
                    connection_id = result.get("connection_id")
                    launch_url = result.get("client_url")
                    guac_token = result.get("token")
                else:
                    warning = result.get("error") or "Remote desktop gateway did not create a connection"
            except Exception as error:
                warning = str(error)
        elif use_html5_gateway:
            warning = "Remote desktop gateway is not configured"

        if require_remote_app and not launch_url:
            return {
                "success": False,
                "error": warning or "RemoteApp connection could not be created",
            }, 502

        session = RdpSession.create({
            "user_id": _object_id(user_id) or user_id,
            "server_id": server.get("_id"),
            "published_app_id": launch_app.get("_id") if launch_app else None,
            "guac_token": guac_token,
            "guac_connection_id": connection_id,
            "launch_url": launch_url,
            "reconnect_token": token_urlsafe(24),
            "connection_type": display_mode,
            "display_mode": display_mode,
            "launch_mode": launch_mode,
            "native_remote_app": bool(native_remote_app),
            "rdp_file_expires_at": (
                datetime.utcnow() + timedelta(minutes=2)
                if native_remote_app
                else None
            ),
            "rdp_file_downloaded_at": None,
            "windows_username": rdp_identity.get("username"),
            "windows_domain": rdp_identity.get("domain"),
            "session_isolation": rdp_identity.get("mode"),
            "is_isolated_session": rdp_identity.get("isolated"),
            "status": "active" if connection_id else "pending",
            "ip_address": ip_address,
            "user_agent": user_agent,
            "client_fingerprint": (
                request.headers.get("X-Client-Fingerprint")
                if has_request_context()
                else None
            ),
        })
        session_id = str(session.get("_id"))

        response = {
            "success": True,
            "message": (
                "Launch request created"
                if connection_id
                else "Downloading remote desktop file"
                if not use_html5_gateway
                else warning
            ),
            "session": _session_response(session),
            "connection_id": connection_id,
            "launch_url": launch_url,
            "session_id": session_id,
            "display_mode": display_mode,
            "launch_mode": launch_mode,
            "launch_transport": (
                "html5"
                if launch_url
                else "rdp_remote_app"
                if native_remote_app
                else "rdp_file"
                if not use_html5_gateway
                else None
            ),
            "session_isolation": rdp_identity.get("mode"),
            "is_isolated_session": rdp_identity.get("isolated"),
        }
        if not use_html5_gateway:
            response["rdp_file_url"] = (
                f"/api/lr/sessions/{session.get('_id')}/file.rdp"
                if native_remote_app
                else f"{_external_base_url()}/portal/api/sessions/{session.get('_id')}/rdp-file"
            )
        if warning:
            response["warning"] = warning
            response["setup_required"] = not _guacamole_configured()

        AuditService.log(
            "session.launch.created",
            user_id=user_id,
            category="session",
            server_id=server.get("_id"),
            session_id=session_id,
            ip_address=ip_address,
            success=True,
            metadata={
                "app_id": str(launch_app.get("_id")) if launch_app else None,
                "display_mode": display_mode,
                "session_isolation": rdp_identity.get("mode"),
                "transport": response.get("launch_transport"),
                "warning": warning,
            },
        )
        return response, 200

    @staticmethod
    def reconnect_session(session_id, user, ip_address, user_agent):
        allowed, reason, session = AccessPolicyService.can_reconnect_session(user, session_id)
        if not allowed:
            AuditService.log(
                "session.reconnect.denied",
                user=user,
                category="session",
                session_id=session_id,
                ip_address=ip_address,
                success=False,
                reason=reason,
            )
            return {"success": False, "error": reason}, 403 if session else 404

        if session is None:
            return {"success": False, "error": "Session not found"}, 404

        RdpSession.collection.update_one(
            {"_id": session["_id"]},
            {
                "$set": {
                    "last_seen_at": datetime.utcnow(),
                    "reconnected_at": datetime.utcnow(),
                    "reconnect_user_agent": user_agent,
                    "reconnect_ip_address": ip_address,
                }
            }
        )
        launch_url = session.get("launch_url")
        if session.get("guac_connection_id"):
            from backend.manager.guacamole_manager import get_guac_client

            client = get_guac_client()
            guac_token = client.get_admin_token()
            if guac_token:
                RdpSession.collection.update_one(
                    {"_id": session["_id"]},
                    {"$set": {"guac_token": guac_token}},
                )
                launch_url = client.build_client_url(
                    str(session.get("guac_connection_id")),
                    guac_token,
                )
        response = {
            "success": True,
            "message": "Session recovered",
            "session": _session_response(session),
            "session_id": str(session.get("_id")),
            "launch_url": launch_url,
            "launch_transport": "html5" if launch_url else "rdp_file",
            "session_isolation": session.get("session_isolation"),
            "is_isolated_session": bool(session.get("is_isolated_session")),
        }
        if not launch_url:
            response["rdp_file_url"] = (
                f"{_external_base_url()}/portal/api/sessions/{session.get('_id')}/rdp-file"
            )

        AuditService.log(
            "session.reconnect.success",
            user=user,
            category="session",
            server_id=session.get("server_id"),
            session_id=str(session.get("_id")),
            ip_address=ip_address,
            success=True,
        )
        return response, 200

    @staticmethod
    def get_rdp_file(session_id, user_id, require_native=False, consume_native=True):
        session_object_id = _object_id(session_id)
        if not session_object_id:
            return None, "Session not found", 404

        session = RdpSession.collection.find_one({
            "_id": session_object_id,
            "user_id": {"$in": _id_variants(user_id)},
        })
        if not session:
            return None, "Session not found", 404

        native_remote_app = bool(session.get("native_remote_app"))
        if require_native and not native_remote_app:
            return None, "RDP file endpoint requires a RemoteApp session", 409
        if native_remote_app:
            expires_at = session.get("rdp_file_expires_at")
            if expires_at and expires_at < datetime.utcnow():
                return None, "RemoteApp file link has expired", 401
            if consume_native and session.get("rdp_file_downloaded_at"):
                return None, "RemoteApp file has already been downloaded", 409

        server = Server.get_by_id(session.get("server_id"))
        if not server or server.get("is_active") is False:
            return None, "Server not found", 404

        app = None
        if session.get("published_app_id"):
            app = PublishedApp.get_by_id(
                session.get("published_app_id"),
                session.get("tenant_id"),
            )
        if native_remote_app and not app:
            return None, "Published RemoteApp is not available", 404

        host = server.get("host") or server.get("ip_address")
        if not str(host or "").strip():
            return None, "Assigned server is missing its RDP address", 400
        try:
            port = int(server.get("port") or 3389)
        except (TypeError, ValueError):
            return None, "Assigned server has an invalid RDP port", 400
        if not 1 <= port <= 65535:
            return None, "Assigned server has an invalid RDP port", 400
        address = f"{host}:{port}" if port != 3389 else host
        username = session.get("windows_username") or server.get("username")
        domain = (
            session.get("windows_domain")
            or server.get("windows_domain")
            or server.get("domain")
            or server.get("hostname")
        )
        rdp_username = _rdp_login_name(username, domain)
        lines = [
            "screen mode id:i:2",
            "use multimon:i:0",
            "desktopwidth:i:1280",
            "desktopheight:i:800",
            "session bpp:i:32",
            "compression:i:1",
            "keyboardhook:i:2",
            "audiomode:i:0",
            "redirectclipboard:i:1",
            "redirectprinters:i:0",
            "administrative session:i:0",
            "disableconnectionsharing:i:0",
            "prompt for credentials:i:0",
            "promptcredentialonce:i:1",
            "enablecredsspsupport:i:1",
            "authentication level:i:2",
            _rdp_line("full address", address),
            _rdp_line("username", rdp_username),
        ]

        if native_remote_app:
            remote_app_lines = _native_remote_app_rdp_lines(app)
            if not remote_app_lines:
                return None, "Published application is missing its RemoteApp program", 409
            lines.extend(remote_app_lines)
        elif app:
            display_mode = session.get("display_mode") or _display_mode(app)
            launch_mode = _launch_mode(app, display_mode)
            if display_mode != "full_desktop":
                remote_app_program = (app.get("remote_app_program") or "").strip()
                initial_program = (app.get("initial_program") or remote_app_program or app.get("target") or "").strip()

                item_type = str(app.get("item_type") or app.get("type") or "").strip().lower()
                folder_path = app.get("folder_path")
                is_folder = item_type == "folder" or bool(folder_path) or "folder-" in (app.get("remote_app_alias") or "") or "folder-" in remote_app_program

                if launch_mode == "remote_app" and remote_app_program.startswith("||") and not is_folder:
                    lines.extend([
                        _rdp_int_line("remoteapplicationmode", 1),
                        _rdp_line("remoteapplicationprogram", remote_app_program),
                        _rdp_line("remoteapplicationname", app.get("remote_app_alias") or app.get("name")),
                        _rdp_line("remoteapplicationcmdline", app.get("arguments")),
                    ])
                elif initial_program:
                    initial_program = _published_program_path(app, initial_program, username)
                    initial_program = _folder_program(app, initial_program)
                    lines.extend([
                        _rdp_line("alternate shell", initial_program),
                        _rdp_line("shell working directory", _working_directory(
                            initial_program,
                            app.get("working_directory"),
                        )),
                    ])

        filename = f"{(app or server).get('name', 'lr-remote')}.rdp"
        safe_filename = "".join(char if char.isalnum() or char in "._-" else "_" for char in filename)
        content = "\r\n".join(lines) + "\r\n"
        if native_remote_app and consume_native:
            consumed = RdpSession.collection.update_one(
                {
                    "_id": session_object_id,
                    "user_id": {"$in": _id_variants(user_id)},
                    "$or": [
                        {"rdp_file_downloaded_at": None},
                        {"rdp_file_downloaded_at": {"$exists": False}},
                    ],
                },
                {"$set": {"rdp_file_downloaded_at": datetime.utcnow()}},
            )
            if consumed.matched_count != 1:
                return None, "RemoteApp file has already been downloaded", 409
        return {
            "content": content,
            "filename": safe_filename,
        }, None, 200

    @staticmethod
    def get_my_sessions(user_id):
        sessions = list(
            RdpSession.collection.find({"user_id": {"$in": _id_variants(user_id)}})
            .sort("started_at", -1)
            .limit(200)
        )
        return {
            "success": True,
            "sessions": RdpSession.to_dict_many(sessions)
        }, 200

    @staticmethod
    def get_session_stats(user_id):
        filter_query = {}
        if user_id:
            filter_query["user_id"] = {"$in": _id_variants(user_id)}

        active_query = dict(filter_query)
        active_query["status"] = "active"

        return {
            "success": True,
            "active": RdpSession.collection.count_documents(active_query),
            "total": RdpSession.collection.count_documents(filter_query)
        }, 200

    @staticmethod
    def get_client_exe_path():
        return os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "static",
                "client",
                "lr_remote_access_client.exe",
            )
        )

    @staticmethod
    def get_admin_panel_exe_path():
        return os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "static",
                "admin",
                "Admin Panel.exe",
            )
        )
