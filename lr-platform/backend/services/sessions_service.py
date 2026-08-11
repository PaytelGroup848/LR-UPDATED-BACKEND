from datetime import datetime

from backend.models.rdp_session import RdpSession
from backend.services.access_policy_service import AccessPolicyService
from backend.services.audit_service import AuditService
from backend.services.portal_service import PortalService


def _session_response(session):
    return RdpSession.to_dict(session)


class SessionsService:

    @staticmethod
    def _cleanup_guacamole_connection(session):
        connection_id = (session or {}).get("guac_connection_id")
        if not connection_id:
            return {"success": True}
        try:
            from backend.manager.guacamole_manager import get_guac_client

            return get_guac_client().delete_connection(str(connection_id))
        except Exception as error:
            return {"success": False, "error": str(error)}

    @staticmethod
    def list_sessions(args, user=None):
        args = args or {}
        query = {}
        if user and user.get("tenant_id"):
            query["tenant_id"] = user.get("tenant_id")
        status = args.get("status")
        user_id = args.get("user_id")
        if status:
            query["status"] = status
        if user_id:
            query["user_id"] = user_id
        if user and not AccessPolicyService.has_role(user, "Admin"):
            from backend.services.portal_service import _id_variants

            query["user_id"] = {"$in": _id_variants(user.id)}

        try:
            limit = min(max(int(args.get("limit", 200)), 1), 1000)
        except (TypeError, ValueError):
            limit = 200
        sessions = list(RdpSession.collection.find(query).sort("started_at", -1).limit(limit))
        return {
            "success": True,
            "sessions": RdpSession.to_dict_many(sessions),
            "count": len(sessions)
        }, 200

    @staticmethod
    def get_stats(user=None):
        return PortalService.get_session_stats(user.id if user else None)

    @staticmethod
    def get_session(session_id, user=None):
        allowed, reason, session = AccessPolicyService.can_view_session(user, session_id)
        if not allowed:
            return {"success": False, "error": reason}, 403 if session else 404
        return {"success": True, "session": _session_response(session)}, 200

    @staticmethod
    def get_my_sessions(user_id):
        return PortalService.get_my_sessions(user_id)

    @staticmethod
    def launch_session(data, user_id, ip_address, user_agent):
        app_id = (data or {}).get("app_id") or (data or {}).get("application_id")
        if app_id:
            return PortalService.launch_app(app_id, user_id, ip_address, user_agent, data=data)
        return PortalService.launch_server(data or {}, user_id, ip_address, user_agent)

    @staticmethod
    def kill_session(session_id, user_id, ip_address):
        from backend.services.portal_service import _object_id

        user = None
        from backend.models.user import User

        user = User.get_by_id(user_id)
        allowed, reason, session = AccessPolicyService.can_view_session(user, session_id)
        if not allowed:
            AuditService.log(
                "session.kill.denied",
                user=user,
                category="session",
                session_id=session_id,
                ip_address=ip_address,
                success=False,
                reason=reason,
            )
            return {"success": False, "error": reason}, 403 if session else 404

        object_id = _object_id(session_id)
        if not object_id:
            return {"success": False, "error": "Session not found"}, 404

        query = {"_id": object_id}
        if user and user.get("tenant_id"):
            query["tenant_id"] = user.get("tenant_id")
        now = datetime.utcnow()
        result = RdpSession.collection.update_one(
            query,
            {
                "$set": {
                    "status": "closed",
                    "ended_at": now,
                    "browser_launch_used_at": now,
                },
                "$unset": {
                    "guac_token": "",
                    "launch_url": "",
                    "browser_launch_nonce_hash": "",
                },
            },
        )
        if result.matched_count == 0:
            return {"success": False, "error": "Session not found"}, 404
        cleanup = SessionsService._cleanup_guacamole_connection(session)
        if not cleanup.get("success"):
            AuditService.log(
                "session.guacamole_cleanup.failed",
                user=user,
                category="session",
                session_id=session_id,
                success=False,
                reason=cleanup.get("error") or "Guacamole cleanup failed",
            )
        AuditService.log(
            "session.kill",
            user=user,
            category="session",
            session_id=session_id,
            ip_address=ip_address,
            success=True,
        )
        return {"success": True, "message": "Session closed"}, 200

    @staticmethod
    def close_user_sessions(user_id, reason="logout"):
        from backend.services.portal_service import _id_variants

        sessions = list(RdpSession.collection.find({
            "user_id": {"$in": _id_variants(user_id)},
            "status": {"$in": ["active", "pending"]},
        }))
        now = datetime.utcnow()
        cleaned = 0
        cleanup_failures = 0
        for session in sessions:
            cleanup = SessionsService._cleanup_guacamole_connection(session)
            if cleanup.get("success"):
                cleaned += 1
            else:
                cleanup_failures += 1
            RdpSession.collection.update_one(
                {"_id": session.get("_id")},
                {
                    "$set": {
                        "status": "closed",
                        "ended_at": now,
                        "browser_launch_used_at": now,
                        "close_reason": reason,
                    },
                    "$unset": {
                        "guac_token": "",
                        "launch_url": "",
                        "browser_launch_nonce_hash": "",
                    },
                },
            )
        return {
            "success": cleanup_failures == 0,
            "closed": len(sessions),
            "gateway_connections_cleaned": cleaned,
            "cleanup_failures": cleanup_failures,
        }

    @staticmethod
    def ping_session(session_id, user=None):
        allowed, reason, session = AccessPolicyService.can_view_session(user, session_id)
        if not allowed:
            return {"success": False, "error": reason}, 403 if session else 404
        result = RdpSession.ping(str(session_id))
        if result.matched_count == 0:
            return {"success": False}, 404
        return {"success": True}, 200

    @staticmethod
    def reconnect_session(session_id, user, ip_address, user_agent):
        return PortalService.reconnect_session(session_id, user, ip_address, user_agent)
