from datetime import datetime
from typing import Any


class MongoDocument:
    collection_name = ""
    _id: Any
    _numeric_id: int | None

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    @property
    def id(self):
        value = getattr(self, "_id", None)
        return str(value) if value is not None else getattr(self, "_numeric_id", None)

    @classmethod
    def from_mongo(cls, document: dict[str, Any] | None):
        if not document:
            return None
        return cls(**document)

    def to_mongo(self):
        return {
            key: value
            for key, value in self.__dict__.items()
            if key not in {"product_key"} and value is not None
        }


class ProductKey(MongoDocument):
    key_code: str
    plan_name: str
    max_activations: int
    valid_days: int
    is_revoked: bool
    issued_to: str | None
    created_by_id: str | int | None
    created_at: datetime | None
    updated_at: datetime | None

    def __init__(
        self,
        key_code: str,
        plan_name: str = "STANDARD",
        max_activations: int = 1,
        valid_days: int = 365,
        is_revoked: bool = False,
        issued_to: str | None = None,
        created_by_id: str | int | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        **kwargs,
    ):
        super().__init__(
            key_code=key_code,
            plan_name=plan_name,
            max_activations=max_activations,
            valid_days=valid_days,
            is_revoked=is_revoked,
            issued_to=issued_to,
            created_by_id=created_by_id,
            created_at=created_at or datetime.utcnow(),
            updated_at=updated_at,
            **kwargs,
        )


class LicenseActivation(MongoDocument):
    product_key_id: str
    device_id: str
    device_name: str | None
    activated_at: datetime | None
    expires_at: datetime | None
    is_active: bool
    product_key: ProductKey | None

    def __init__(
        self,
        product_key_id: str,
        device_id: str,
        device_name: str | None = None,
        activated_at: datetime | None = None,
        expires_at: datetime | None = None,
        is_active: bool = True,
        device_fingerprint_hash: str | None = None,
        fingerprint: dict | None = None,
        revoked_at: datetime | None = None,
        revoked_reason: str | None = None,
        **kwargs,
    ):
        super().__init__(
            product_key_id=product_key_id,
            device_id=device_id,
            device_name=device_name,
            activated_at=activated_at or datetime.utcnow(),
            expires_at=expires_at,
            is_active=is_active,
            device_fingerprint_hash=device_fingerprint_hash,
            fingerprint=fingerprint,
            revoked_at=revoked_at,
            revoked_reason=revoked_reason,
            **kwargs,
        )


class TrialSession(MongoDocument):
    device_id: str
    started_at: datetime | None
    expires_at: datetime | None
    is_held: bool
    held_at: datetime | None
    held_context: str | None

    def __init__(
        self,
        device_id: str,
        started_at: datetime | None = None,
        expires_at: datetime | None = None,
        is_held: bool = False,
        held_at: datetime | None = None,
        held_context: str | None = None,
        device_fingerprint_hash: str | None = None,
        machine_guid_hash: str | None = None,
        disk_serial_hash: str | None = None,
        public_ip_history: list[str] | None = None,
        first_seen_at: datetime | None = None,
        trial_started_at: datetime | None = None,
        trial_used: bool = True,
        fingerprint: dict | None = None,
        **kwargs,
    ):
        super().__init__(
            device_id=device_id,
            started_at=started_at or datetime.utcnow(),
            expires_at=expires_at,
            is_held=is_held,
            held_at=held_at,
            held_context=held_context,
            device_fingerprint_hash=device_fingerprint_hash,
            machine_guid_hash=machine_guid_hash,
            disk_serial_hash=disk_serial_hash,
            public_ip_history=public_ip_history or [],
            first_seen_at=first_seen_at or started_at or datetime.utcnow(),
            trial_started_at=trial_started_at or started_at or datetime.utcnow(),
            trial_used=trial_used,
            fingerprint=fingerprint,
            **kwargs,
        )
