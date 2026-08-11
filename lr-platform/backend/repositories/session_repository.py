from backend.models.rdp_session import RdpSession


class SessionRepository:
    def __init__(self, db=None):
        self.collection = RdpSession.collection if db is None else db["rdp_sessions"]

    def get_all(self):
        return list(self.collection.find().sort("started_at", -1))

    def get_by_id(self, session_id):
        from bson import ObjectId

        try:
            return self.collection.find_one({"_id": ObjectId(str(session_id))})
        except Exception:
            return None

    def create(self, data):
        return RdpSession.create(data)

    def close(self, session_id):
        return RdpSession.close(str(session_id))

    def ping(self, session_id):
        return RdpSession.ping(str(session_id))
