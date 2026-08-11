from backend.models.activity_log import ActivityLog


class AuditService:
    @staticmethod
    def log(
        action,
        *,
        user=None,
        user_id=None,
        category="system",
        server_id=None,
        session_id=None,
        ip_address=None,
        success=True,
        reason=None,
        metadata=None,
    ):
        actor_id = user_id or getattr(user, "id", None)
        actor_role = getattr(user, "role", None) if user is not None else None
        tenant_id = user.get("tenant_id") if isinstance(user, dict) else getattr(user, "tenant_id", None)
        if not tenant_id and actor_id:
            from backend.models.user import User
            actor = User.get_by_id(actor_id)
            tenant_id = actor.get("tenant_id") if actor else None
        return ActivityLog.log(
            tenant_id=tenant_id,
            user_id=actor_id,
            action=action,
            category=category,
            server_id=server_id,
            session_id=session_id,
            ip_address=ip_address,
            success=success,
            reason=reason,
            actor_role=actor_role,
            metadata=metadata or {},
        )

    @staticmethod
    def list(limit=100, user_id=None, tenant_id=None):
        return [
            ActivityLog.to_dict(item)
            for item in ActivityLog.recent(limit, user_id=user_id, tenant_id=tenant_id)
        ]
