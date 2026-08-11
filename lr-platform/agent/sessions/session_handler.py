from agent.sessions.session_tracker import SessionTracker


class SessionHandler:
    def __init__(self, tracker=None):
        self.tracker = tracker or SessionTracker()

    def handle_start(self, payload):
        payload = payload or {}
        session_id = payload.get("session_id") or payload.get("id")
        if not session_id:
            raise ValueError("session_id is required")
        return self.tracker.start(session_id, **payload)

    def handle_ping(self, payload):
        payload = payload or {}
        return self.tracker.touch(payload.get("session_id") or payload.get("id"))

    def handle_stop(self, payload):
        payload = payload or {}
        return self.tracker.close(payload.get("session_id") or payload.get("id"))
