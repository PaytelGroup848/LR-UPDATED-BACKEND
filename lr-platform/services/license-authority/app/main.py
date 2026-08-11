import os
from datetime import datetime

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pymongo import MongoClient, ReturnDocument


MONGODB_URL = os.environ["MONGODB_URL"]
DATABASE_NAME = os.getenv("SUPER_ADMIN_MONGODB_DATABASE", "test")
COLLECTION_NAME = os.getenv("SUPER_ADMIN_LICENSE_COLLECTION", "lr_license_keys")

client = MongoClient(
    MONGODB_URL,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=10000,
    retryReads=True,
    retryWrites=True,
)
database = client[DATABASE_NAME]
licenses = database[COLLECTION_NAME]

app = FastAPI(title="LR License Authority", version="1.0.0")


class LicenseValidationRequest(BaseModel):
    key: str


def _iso_utc(value):
    if not isinstance(value, datetime):
        return None
    return value.isoformat(timespec="milliseconds") + ("Z" if value.tzinfo is None else "")


@app.get("/health")
def health():
    try:
        client.admin.command("ping")
    except Exception as error:
        return JSONResponse(
            status_code=503,
            content={
                "service": "license-authority",
                "status": "degraded",
                "database": "unavailable",
                "error": str(error),
            },
        )
    return {"service": "license-authority", "status": "ok"}


@app.post("/public/keys/validate")
def validate_key(payload: LicenseValidationRequest):
    key = payload.key.strip().upper()
    if not key:
        return {
            "success": True,
            "data": {"valid": False, "status": "not_found", "expiresAt": None},
        }

    document = licenses.find_one({"key": key})
    if not document:
        return {
            "success": True,
            "data": {"valid": False, "status": "not_found", "expiresAt": None},
        }

    now = datetime.utcnow()
    expires_at = document.get("expiresAt")
    status = str(document.get("status") or "invalid").strip().lower()
    if isinstance(expires_at, datetime) and expires_at <= now:
        status = "expired"

    # Partner/bulk keys are created as "unassigned". Their first successful
    # validation atomically consumes the pool entry, so a freshly generated
    # key works without a separate manual status change.
    if status == "unassigned" and isinstance(expires_at, datetime) and expires_at > now:
        claimed = licenses.find_one_and_update(
            {
                "_id": document["_id"],
                "status": "unassigned",
                "expiresAt": {"$gt": now},
            },
            {
                "$set": {
                    "status": "active",
                    "activatedAt": now,
                    "lastValidatedAt": now,
                    "updatedAt": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if claimed:
            document = claimed
            expires_at = document.get("expiresAt")
            status = str(document.get("status") or "invalid").strip().lower()
        else:
            # Another request may have won the claim. Validate its final state
            # instead of returning a race-dependent failure.
            document = licenses.find_one({"_id": document["_id"]}) or document
            expires_at = document.get("expiresAt")
            status = str(document.get("status") or "invalid").strip().lower()
            if isinstance(expires_at, datetime) and expires_at <= now:
                status = "expired"

    valid = status == "active" and isinstance(expires_at, datetime) and expires_at > now
    if valid:
        licenses.update_one(
            {"_id": document["_id"]},
            {"$set": {"lastValidatedAt": now, "updatedAt": now}},
        )

    return {
        "success": True,
        "data": {
            "valid": valid,
            "status": status,
            "expiresAt": _iso_utc(expires_at),
        },
    }
