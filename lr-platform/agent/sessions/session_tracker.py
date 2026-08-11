from datetime import datetime


class SessionTracker:
    def __init__(self):
        self.sessions = {}

    def start(self, session_id, **metadata):
        self.sessions[str(session_id)] = {
            "session_id": str(session_id),
            "status": "active",
            "started_at": datetime.utcnow(),
            "last_seen_at": datetime.utcnow(),
            **metadata,
        }
        return self.sessions[str(session_id)]

    def touch(self, session_id):
        session = self.sessions.get(str(session_id))
        if session:
            session["last_seen_at"] = datetime.utcnow()
        return session

    def close(self, session_id, status="closed"):
        session = self.sessions.get(str(session_id))
        if session:
            session["status"] = status
            session["ended_at"] = datetime.utcnow()
        return session

    def all(self):
        return list(self.sessions.values())
