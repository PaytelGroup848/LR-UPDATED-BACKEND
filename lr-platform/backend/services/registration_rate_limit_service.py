from datetime import datetime, timedelta
import hashlib

from backend.core.config import settings
from backend.extensions import db


class RegistrationRateLimitService:
    collection = db["registration_rate_limits"]

    @classmethod
    def check_and_record(cls, remote_address):
        scope = str(remote_address or "unknown")
        scope_hash = hashlib.sha256(scope.encode("utf-8")).hexdigest()
        now = datetime.utcnow()
        window = max(int(settings.REGISTRATION_RATE_LIMIT_WINDOW_SECONDS), 60)
        maximum = max(int(settings.REGISTRATION_RATE_LIMIT_MAX_ATTEMPTS), 1)
        document = cls.collection.find_one({"scope_hash": scope_hash, "expires_at": {"$gt": now}})
        if document and int(document.get("attempts", 0)) >= maximum:
            return False
        if document:
            cls.collection.update_one({"_id": document["_id"]}, {"$inc": {"attempts": 1}})
        else:
            cls.collection.update_one(
                {"scope_hash": scope_hash},
                {"$set": {"attempts": 1, "created_at": now, "expires_at": now + timedelta(seconds=window)}},
                upsert=True,
            )
        return True
