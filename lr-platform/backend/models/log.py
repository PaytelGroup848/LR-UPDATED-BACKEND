from datetime import datetime

from backend.extensions import db


class Log:
    collection = db["logs"]

    @staticmethod
    def create(level, message, **metadata):
        document = {
            "level": str(level or "info").lower(),
            "message": str(message or ""),
            "created_at": datetime.utcnow(),
            **metadata,
        }
        result = Log.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return document

    @staticmethod
    def latest(limit=100, level=None):
        query = {"level": level} if level else {}
        return list(Log.collection.find(query).sort("created_at", -1).limit(int(limit)))

    @staticmethod
    def to_dict(document):
        return {
            "id": str(document.get("_id")) if document.get("_id") else None,
            "level": document.get("level"),
            "message": document.get("message"),
            "created_at": document.get("created_at").isoformat() if document.get("created_at") else None,
            "metadata": {
                key: value
                for key, value in document.items()
                if key not in {"_id", "level", "message", "created_at"}
            },
        }
