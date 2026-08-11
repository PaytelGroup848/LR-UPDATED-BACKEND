import os


from datetime import datetime, timedelta
from secrets import token_urlsafe
from urllib.parse import urlencode, urljoin, urlparse, urlunparse

from bson import ObjectId
from flask import current_app, request

from backend.models.login_link import LoginLink
from backend.models.tenant import Tenant, normalize_company_code
from backend.models.user import User
from backend.extensions import db
from backend.extensions import socketio
from backend.manager.stream_manager import stream_manager
from backend.services.access_policy_service import AccessPolicyService
from backend.services.audit_service import AuditService
from backend.services.monitoring_service import MonitoringService
from backend.services.secure_file_transfer_service import SecureFileTransferService


def _object_id(value):
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return None


def _as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"false", "0", "no", "off"}


def _tenant_id(user):
    if user is None or getattr(user, "is_anonymous", False):
        return None
    getter = getattr(user, "get", None)
    return getter("tenant_id") if callable(getter) else None


def _matching_agent_sid(user):
    try:
        from backend.sockets.agent_socket import connected_agents
    except Exception:
        return None, None

    usernames = {
        str(user.get("username") or "").lower(),
        str(user.get("windows_username") or "").lower(),
    }
    usernames.discard("")
    for sid, info in connected_agents.items():
        if str(info.get("username") or "").lower() in usernames:
            return sid, info
    return None, None


def _public_base_url():
    return request.host_url.rstrip("/")


def _frontend_base_url(payload):
    configured_url = (
        payload.get("frontend_url")
        or current_app.config.get("FRONTEND_URL")
    )
    if configured_url:
        return str(configured_url).rstrip("/")

    parsed = urlparse(_public_base_url())
    if parsed.hostname in {"127.0.0.1", "localhost"} and parsed.port in {8000, 8001, 8002, 8003}:
        netloc = f"{parsed.hostname}:3000"
        return urlunparse((parsed.scheme, netloc, "", "", "", "")).rstrip("/")

    return _public_base_url()


class AdminFeatureService:
    @staticmethod
    def generate_portal_url(current_user, ip_address=None):
        tenant_id = current_user.get("tenant_id")
        tenant = Tenant.get_by_id(tenant_id)
        if not tenant or not tenant.get("is_active"):
            return {
                "success": False,
                "error": "Company account is inactive or unavailable",
            }, 423

        company_code = normalize_company_code(
            tenant.get("company_code") or tenant.get("company_slug")
        )
        if not company_code:
            return {
                "success": False,
                "error": "Company code is not configured",
            }, 423

        frontend_base_url = _frontend_base_url({})
        login_page_url = urljoin(f"{frontend_base_url}/", "login")
        url = f"{login_page_url}?{urlencode({'company_code': company_code})}"
        AuditService.log(
            "portal_login_url.generated",
            user=current_user,
            category="portal_customization",
            ip_address=ip_address,
            metadata={"company_code": company_code},
        )
        return {
            "success": True,
            "message": "Company login portal URL generated",
            "url": url,
            "company_code": company_code,
        }, 200

    @staticmethod
    def get_user_policy(user_id):
        user = User.get_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}, 404

        policy = db["user_policies"].find_one({"user_id": str(user_id)})
        if not policy:
            return {
                "success": True,
                "policy": {},
                "enforcement_status": "not_configured",
                "message": "No policy saved for this user",
            }, 200

        return {
            "success": True,
            "policy": policy.get("policy") or {},
            "updated_at": policy.get("updated_at").isoformat() if policy.get("updated_at") else None,
            "enforcement_status": policy.get("enforcement_status") or "saved_only",
            "enforcement_result": policy.get("enforcement_result"),
            "agent_id": policy.get("agent_id"),
            "message": policy.get("message") or "Policy is saved in database; endpoint/agent enforcement is not connected yet.",
        }, 200

    @staticmethod
    def save_user_policy(user_id, payload, actor=None, ip_address=None):
        user = User.get_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}, 404

        policy = (payload or {}).get("policy") or {}
        now = datetime.utcnow()
        target_username = user.get("windows_username") or user.get("username")
        agent_sid, agent_info = _matching_agent_sid(user)
        enforcement_status = "saved_only"
        enforcement_message = "Policy saved in database. No matching online agent was found for live enforcement."
        enforcement_result = None

        if agent_sid:
            try:
                enforcement_result = socketio.call(
                    "apply_policy",
                    {
                        "agent_id": agent_info.get("agent_id"),
                        "target_username": target_username,
                        "policy": policy,
                    },
                    namespace="/agent",
                    to=agent_sid,
                    timeout=45,
                )
                if enforcement_result and enforcement_result.get("success"):
                    enforcement_status = "applied"
                    enforcement_message = "Policy saved and applied by the online Windows agent."
                else:
                    enforcement_status = "partial_or_failed"
                    enforcement_message = (
                        enforcement_result.get("message")
                        if isinstance(enforcement_result, dict)
                        else "Agent returned an invalid policy response."
                    )
            except Exception as error:
                enforcement_status = "push_failed"
                enforcement_message = f"Policy saved, but agent enforcement failed: {error}"

        document = {
            "user_id": str(user_id),
            "policy": policy,
            "updated_at": now,
            "updated_by": str(getattr(actor, "id", "") or ""),
            "target_username": target_username,
            "agent_id": (agent_info or {}).get("agent_id"),
            "enforcement_status": enforcement_status,
            "enforcement_result": enforcement_result,
            "message": enforcement_message,
        }
        db["user_policies"].update_one(
            {"user_id": str(user_id)},
            {"$set": document, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        AuditService.log(
            "policy.save",
            user=actor,
            category="policy",
            ip_address=ip_address,
            success=True,
            metadata={"target_user_id": str(user_id), "policy": policy},
        )
        return {"success": True, **document}, 200

    @staticmethod
    def setup_2fa(user, ip_address):
        return {
            "success": False,
            "error": "2FA dependencies are not wired yet"
        }

    @staticmethod
    def enable_2fa(user, token, ip_address):
        return {
            "success": False,
            "error": "2FA dependencies are not wired yet"
        }

    @staticmethod
    def disable_2fa(user, ip_address):
        return {
            "success": False,
            "error": "2FA dependencies are not wired yet"
        }

    @staticmethod
    def get_tickets(user, is_manager=False, status=None):
        return {
            "success": True,
            "tickets": []
        }

    @staticmethod
    def create_ticket(user, payload, ip_address):
        return {
            "success": False,
            "error": "Ticket dependencies are not wired yet"
        }, 501

    @staticmethod
    def update_ticket(ticket_id, user, payload, ip_address, is_manager=False):
        return {
            "success": False,
            "error": "Ticket dependencies are not wired yet"
        }, 501

    @staticmethod
    def get_clipboard_items(user, session_id=None):
        return {
            "success": True,
            "items": []
        }

    @staticmethod
    def create_clipboard_item(user, payload, ip_address):
        return {
            "success": False,
            "error": "Clipboard dependencies are not wired yet"
        }, 501

    @staticmethod
    def get_transfers():
        listing = SecureFileTransferService.list_files(".")
        return {
            "success": True,
            "files": listing.get("items", [])
        }

    @staticmethod
    def upload_transfer(user, uploaded_file, ip_address):
        if hasattr(uploaded_file, "get"):
            uploaded_file = uploaded_file.get("file")
        try:
            result = SecureFileTransferService.upload(uploaded_file, ".")
            return {"success": True, **result}, 201
        except (OSError, ValueError) as error:
            return {"success": False, "error": str(error)}, 400

    @staticmethod
    def download_transfer(user, name, ip_address):
        try:
            return SecureFileTransferService.download_path(name), 200
        except (OSError, ValueError) as error:
            return {"success": False, "error": str(error)}, 404

    @staticmethod
    def get_recordings(user):
        return {
            "success": True,
            "recordings": stream_manager.recordings()
        }

    @staticmethod
    def start_recording(user, agent_id, ip_address, session_id=None):
        allowed, reason = AccessPolicyService.can_record_stream(user, agent_id, session_id=session_id)
        if not allowed:
            AuditService.log(
                "recording.start.denied",
                user=user,
                category="recording",
                session_id=session_id,
                ip_address=ip_address,
                success=False,
                reason=reason,
                metadata={"agent_id": agent_id},
            )
            return {"success": False, "error": reason}, 403

        recording_dir = current_app.config.get("RECORDING_DIR") or os.path.join(
            current_app.instance_path,
            "recordings"
        )
        recording = stream_manager.start_recording(
            agent_id,
            recording_dir,
            user_id=getattr(user, "id", None),
            session_id=session_id,
        )
        AuditService.log(
            "recording.start",
            user=user,
            category="recording",
            session_id=session_id,
            ip_address=ip_address,
            success=True,
            metadata={"agent_id": agent_id, "folder": recording.get("folder")},
        )
        return {
            "success": True,
            "recording": recording,
        }, 200

    @staticmethod
    def stop_recording(user, agent_id, ip_address, session_id=None):
        allowed, reason = AccessPolicyService.can_record_stream(user, agent_id, session_id=session_id)
        if not allowed:
            AuditService.log(
                "recording.stop.denied",
                user=user,
                category="recording",
                session_id=session_id,
                ip_address=ip_address,
                success=False,
                reason=reason,
                metadata={"agent_id": agent_id},
            )
            return {"success": False, "error": reason}, 403

        recording = stream_manager.stop_recording(agent_id, session_id=session_id)
        AuditService.log(
            "recording.stop",
            user=user,
            category="recording",
            session_id=session_id,
            ip_address=ip_address,
            success=True,
            metadata={"agent_id": agent_id, "frame_count": recording.get("frame_count")},
        )
        return {
            "success": True,
            "recording": recording
        }, 200

    @staticmethod
    def get_monitoring(user=None):
        tenant_id = _tenant_id(user)
        return MonitoringService.get_monitoring(tenant_id)

    @staticmethod
    def get_health(user=None):
        tenant_id = _tenant_id(user)
        monitoring = MonitoringService.get_monitoring(tenant_id)
        return {
            "success": True,
            "status": monitoring["health"]["status"],
            "health": monitoring["health"],
            "agents": monitoring["agents"],
            "streams": monitoring["streams"],
            "services": monitoring.get("services", {}),
        }

    @staticmethod
    def get_streams(agent_id=None, user=None):
        tenant_id = _tenant_id(user)
        return {
            "success": True,
            "streams": MonitoringService.get_streams(agent_id, tenant_id)
        }

    @staticmethod
    def get_error_logs(limit=100):
        return {
            "success": True,
            "errors": []
        }

    @staticmethod
    def generate_url(payload, current_user, ip_address):
        user_id = payload.get("user_id")
        expires_minutes = payload.get("expires_minutes", payload.get("expires", 60))
        try:
            expires_minutes = max(1, int(expires_minutes))
        except (TypeError, ValueError):
            expires_minutes = 60

        user_oid = _object_id(user_id) if user_id else None
        if not user_id:
            return {
                "success": False,
                "error": "Select a user before generating a direct login URL"
            }, 400
        tenant_id = current_user.get("tenant_id")
        if not User.get_by_id(user_id, tenant_id=tenant_id):
            return {
                "success": False,
                "error": "User not found"
            }, 404

        tenant = Tenant.get_by_id(tenant_id)
        if not tenant or not tenant.get("is_active"):
            return {
                "success": False,
                "error": "Company account is inactive or unavailable"
            }, 423
        company_code = normalize_company_code(
            tenant.get("company_code") or tenant.get("company_slug")
        )
        if not company_code:
            return {
                "success": False,
                "error": "Company code is not configured"
            }, 423

        token = token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(minutes=expires_minutes)
        link = LoginLink.create(
            token=token,
            user_id=user_oid,
            expires_at=expires_at,
            one_time=_as_bool(payload.get("one_time"), True),
            created_by=_object_id(getattr(current_user, "id", None)) or getattr(current_user, "id", None),
            tenant_id=tenant_id,
        )

        if not link:
            return {
                "success": False,
                "error": "Unable to generate login URL"
            }, 500

        backend_base_url = str(payload.get("base_url") or _public_base_url()).rstrip("/")
        frontend_base_url = _frontend_base_url(payload)
        login_link_url = urljoin(f"{frontend_base_url}/", f"login-link/{token}")
        url = f"{login_link_url}?{urlencode({'company_code': company_code})}"

        return {
            "success": True,
            "message": "Login URL generated",
            "url": url,
            "company_code": company_code,
            "download_url": urljoin(f"{backend_base_url}/", "portal/api/download-client"),
            "link": LoginLink.to_dict(link),
        }, 201

    @staticmethod
    def get_login_links(user, user_id=None, limit=100):
        query = {}
        if user and user.get("tenant_id"):
            query["tenant_id"] = user.get("tenant_id")
        if user_id:
            object_id = _object_id(user_id)
            query["user_id"] = {"$in": [str(user_id), object_id] if object_id else [str(user_id)]}
        try:
            limit = min(max(int(limit), 1), 500)
        except (TypeError, ValueError):
            limit = 100
        links = LoginLink.collection.find(query).sort("created_at", -1).limit(limit)
        return {
            "success": True,
            "links": [LoginLink.to_dict(link) for link in links]
        }

    @staticmethod
    def revoke_login_link(link_id, user_id, ip_address):
        object_id = _object_id(link_id)
        if not object_id:
            return {
                "success": False,
                "error": "Login link not found"
            }

        actor = User.get_by_id(user_id)
        query = {"_id": object_id}
        if actor and actor.get("tenant_id"):
            query["tenant_id"] = actor.get("tenant_id")
        result = LoginLink.collection.update_one(
            query,
            {"$set": {"revoked_at": datetime.utcnow(), "revoked_by": _object_id(user_id) or user_id}}
        )
        if result.matched_count == 0:
            return {
                "success": False,
                "error": "Login link not found"
            }

        return {
            "success": True,
            "message": "Login link revoked"
        }

    @staticmethod
    def test_alert(user_id, ip_address, payload):
        return {
            "success": False,
            "results": []
        }

    @staticmethod
    def get_agent_install_script(server_url):
        server_url = str(server_url or "").rstrip("/")
        command = (
            "$env:LIVEPANEL_SERVER_URL = '" + server_url + "'; "
            "python agent/main.py"
        )
        return {
            "success": True,
            "server_url": server_url,
            "windows_command": command,
            "linux_script": f"export LIVEPANEL_SERVER_URL='{server_url}' && python agent/main.py"
        }

    @staticmethod
    def get_agent_source_path(name):
        return {
            "success": False,
            "error": "File not found"
        }

    @staticmethod
    def get_client_download():
        from backend.services.portal_service import PortalService

        file_path = PortalService.get_client_exe_path()

        if not os.path.exists(file_path):
            return {
                "success": False,
                "error": "Client not found"
            }

        return {
            "success": True,
            "file_path": file_path,
            "download_name": "lr_remote_access_client.exe",
        }

    @staticmethod
    def get_admin_panel_download():
        from backend.services.portal_service import PortalService

        file_path = PortalService.get_admin_panel_exe_path()

        if not os.path.exists(file_path):
            return {
                "success": False,
                "error": "Admin Panel app not found"
            }

        return {
            "success": True,
            "file_path": file_path,
            "download_name": "Admin Panel.exe",
        }
