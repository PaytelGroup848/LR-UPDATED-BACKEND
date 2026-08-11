from datetime import datetime

from bson import ObjectId

from backend.models.license import LicenseActivation
from backend.models.license import ProductKey
from backend.models.license import TrialSession


def _object_id(value):
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception:
        return value


class ProductKeyRepository:
    def __init__(self, db):
        self.collection = db["product_keys"]
        self.collection.create_index("key_code", unique=True)

    def get_by_code(self, key_code: str):
        return ProductKey.from_mongo(self.collection.find_one({"key_code": key_code}))

    def get_all(self):
        return [
            ProductKey.from_mongo(item)
            for item in self.collection.find().sort("created_at", -1)
        ]

    def create(self, product_key: ProductKey):
        document = product_key.to_mongo()
        document.setdefault("created_at", datetime.utcnow())
        result = self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return ProductKey.from_mongo(document)

    def revoke(self, product_key: ProductKey):
        self.collection.update_one(
            {"_id": _object_id(product_key.id)},
            {"$set": {"is_revoked": True, "updated_at": datetime.utcnow()}},
        )
        return self.get_by_code(product_key.key_code)


class LicenseActivationRepository:
    def __init__(self, db):
        self.db = db
        self.collection = db["license_activations"]
        self.keys = db["product_keys"]
        self.collection.create_index(
            [("product_key_id", 1)],
            unique=True,
            partialFilterExpression={"is_active": True},
            name="uniq_active_license_per_product_key",
        )

    def count_active_for_key(self, product_key_id: str) -> int:
        return self.collection.count_documents({
            "product_key_id": str(product_key_id),
            "is_active": True,
        })

    def get_active_for_key(self, product_key_id: str):
        document = self.collection.find_one(
            {
                "product_key_id": str(product_key_id),
                "is_active": True,
            },
            sort=[("activated_at", -1)],
        )
        return LicenseActivation.from_mongo(document)

    def deactivate_for_key(self, product_key_id: str, deactivated_at=None):
        return self.collection.update_many(
            {
                "product_key_id": str(product_key_id),
                "is_active": True,
            },
            {
                "$set": {
                    "is_active": False,
                    "deactivated_at": deactivated_at or datetime.utcnow(),
                }
            },
        )

    def get_by_device(self, device_id: str):
        document = self.collection.find_one(
            {"device_id": device_id, "is_active": True, "revoked_at": {"$exists": False}},
            sort=[("expires_at", -1)],
        )
        activation = LicenseActivation.from_mongo(document)
        if activation:
            key = self.keys.find_one({"_id": _object_id(activation.product_key_id)})
            activation.product_key = ProductKey.from_mongo(key)
        return activation

    def create(self, activation: LicenseActivation):
        document = activation.to_mongo()
        document["product_key_id"] = str(document["product_key_id"])
        document.setdefault("activated_at", datetime.utcnow())
        result = self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return LicenseActivation.from_mongo(document)

    def update_expiry(self, activation: LicenseActivation, expires_at: datetime):
        self.collection.update_one(
            {"_id": _object_id(activation.id)},
            {"$set": {"expires_at": expires_at}},
        )
        activation.expires_at = expires_at
        return activation


class TrialSessionRepository:
    def __init__(self, db):
        self.collection = db["trial_sessions"]
        self.collection.create_index("device_id", unique=True)

    def get_by_device(self, device_id: str):
        return TrialSession.from_mongo(self.collection.find_one({"device_id": device_id}))

    def get_by_fingerprint(self, fingerprint_hash: str | None):
        if not fingerprint_hash:
            return None
        return TrialSession.from_mongo(self.collection.find_one({"device_fingerprint_hash": fingerprint_hash}))

    def create(self, trial: TrialSession):
        document = trial.to_mongo()
        result = self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return TrialSession.from_mongo(document)

    def update(self, trial: TrialSession):
        document = trial.to_mongo()
        trial_id = document.pop("_id", None) or trial.id
        self.collection.update_one(
            {"_id": _object_id(trial_id)},
            {"$set": document},
        )
        return self.get_by_device(trial.device_id)
