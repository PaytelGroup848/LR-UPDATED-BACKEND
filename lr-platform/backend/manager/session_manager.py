import logging
from datetime import datetime, timedelta
from typing import Any, cast


from backend.extensions import db
from backend.models.rdp_session import RdpSession

logger = logging.getLogger(__name__)

SESSION_TIMEOUT_MINUTES = 60


class SessionManager:

    def create_session(
        self,
        user_id,
        server_id,
        guac_token=None,
        guac_connection_id=None,
        connection_type='rdp',
        published_app_id=None,
        ip_address=None,
        user_agent=None,
    ):
        session = RdpSession.create({
            "user_id": user_id,
            "server_id": server_id,
            "published_app_id": published_app_id,
            "guac_token": guac_token,
            "guac_connection_id": guac_connection_id,
            "connection_type": connection_type,
            "status": "active",
            "ip_address": ip_address,
            "user_agent": user_agent,
        })
        logger.info(f"Session created: id={session.get('_id')} user={user_id} server={server_id}")
        return session

    def get_all_active(self):
        return RdpSession.get_active()

    def get_session(self, session_id):
        if session_id is None:
            return None
        try:
            from bson import ObjectId

            return RdpSession.collection.find_one({"_id": ObjectId(str(session_id))})
        except Exception:
            return None

    def get_user_sessions(self, user_id, active_only=False):
        if active_only:
            return list(RdpSession.collection.find({"user_id": user_id,"status": "active" }).sort("started_at", -1)
)
        return RdpSession.get_by_user(user_id)

    def get_server_sessions(self, server_id, active_only=True):
        filter_query = {
            "server_id": server_id
        }

        if active_only:
            filter_query["status"] = "active"

        return list(
            RdpSession.collection.find(filter_query)
            .sort("started_at", -1)
    )

    def get_stats(self):
        return {
            'total': RdpSession.collection.count_documents({}),
            'active': RdpSession.collection.count_documents({
                'status': 'active'
        }),
            'closed': RdpSession.collection.count_documents({
                'status': 'closed'
        }),
            'errors': RdpSession.collection.count_documents({
                'status': 'error'
        }),
    }

    def ping_session(self, session_id):
        session = self.get_session(session_id)
        if session and session.get('status') == 'active':
            RdpSession.ping(session_id)
            return True
        return False

    def update_token(self, session_id, new_token):
        session = self.get_session(session_id)
        if session:
            from bson import ObjectId

            RdpSession.collection.update_one(
                {"_id": ObjectId(str(session_id))},
                {"$set": {"guac_token": new_token}},
            )
            return True
        return False

    def close_session(self, session_id):
        session = self.get_session(session_id)
        if not session:
            return {'success': False, 'error': 'Session not found'}
        if session.get('status') != 'active':
            return {'success': False, 'error': 'Session already closed'}
        RdpSession.close(session_id)
        logger.info(f'Session closed: id={session_id}')
        return {'success': True, 'message': f'Session {session_id} closed'}

    def close_user_sessions(self, user_id):
        sessions = self.get_user_sessions(user_id, active_only=True)
        for s in sessions:
            RdpSession.close(s.get("_id"))
        logger.info(f'Closed {len(sessions)} sessions for user {user_id}')
        return {'success': True, 'closed': len(sessions)}

    def mark_error(self, session_id, detail=''):
        session = self.get_session(session_id)
        if session:
            from bson import ObjectId

            RdpSession.collection.update_one(
                {"_id": ObjectId(str(session_id))},
                {"$set": {"status": "error", "ended_at": datetime.utcnow()}},
            )
            logger.warning(f'Session {session_id} marked error: {detail}')
            return True
        return False

    def cleanup_stale_sessions(self):
        cutoff = datetime.utcnow() - timedelta(minutes=SESSION_TIMEOUT_MINUTES)

        stale_sessions = list(RdpSession.collection.find({
            "status": {"$in": ["active", "pending"]},
            "last_seen_at": {"$lt": cutoff},
        }))
        if not stale_sessions:
            return 0

        from backend.services.sessions_service import SessionsService

        now = datetime.utcnow()
        count = 0
        for session in stale_sessions:
            SessionsService._cleanup_guacamole_connection(session)
            result = RdpSession.collection.update_one(
                {"_id": session.get("_id"), "status": {"$in": ["active", "pending"]}},
                {
                    "$set": {
                        "status": "closed",
                        "ended_at": now,
                        "browser_launch_used_at": now,
                        "close_reason": "expired",
                    },
                    "$unset": {
                        "guac_token": "",
                        "launch_url": "",
                        "browser_launch_nonce_hash": "",
                    },
                },
            )
            count += int(result.modified_count or 0)

        if count:
            logger.info(f"Auto-closed {count} stale sessions")

        return count
