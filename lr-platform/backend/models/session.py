from datetime import datetime
from backend.extensions import db


class Session:

    collection = db["sessions"]

    @staticmethod
    def create(user_id, session_token, status="active"):

        session = {
            "user_id": user_id,
            "session_token": session_token,
            "status": status,
            "created_at": datetime.utcnow()
        }

        # unique token check
        existing = Session.collection.find_one({"session_token": session_token})
        if existing:
            return None

        result = Session.collection.insert_one(session)
        session["_id"] = result.inserted_id
        return session

    @staticmethod
    def get_by_token(session_token):
        return Session.collection.find_one({"session_token": session_token})

    @staticmethod
    def update_status(session_token, status):
        return Session.collection.update_one(
            {"session_token": session_token},
            {"$set": {"status": status}}
        )

    @staticmethod
    def delete(session_token):
        return Session.collection.delete_one({"session_token": session_token})

    @staticmethod
    def get_active():
        return list(Session.collection.find({"status": "active"}))

    @staticmethod
    def to_dict(session):
        return {
            "id": str(session.get("_id")),
            "user_id": session.get("user_id"),
            "session_token": session.get("session_token"),
            "status": session.get("status"),
            "created_at": session.get("created_at").isoformat() if session.get("created_at") else None,
        }