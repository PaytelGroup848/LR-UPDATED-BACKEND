from datetime import datetime
from datetime import timedelta
from math import ceil

from pymongo.errors import DuplicateKeyError

from backend.models.license import LicenseActivation
from backend.models.license import ProductKey
from backend.models.license import TrialSession
from backend.security.license_token import sign_license_token
from backend.services.audit_service import AuditService
from backend.services.external_license_validator import ExternalLicenseValidator


KEY_TRANSFER_LOCK_DAYS = 90


class LicenseService:

    def __init__(
        self,
        key_repository,
        activation_repository,
        trial_repository,
        external_validator=None,
    ):
        self.key_repository = key_repository
        self.activation_repository = activation_repository
        self.trial_repository = trial_repository
        self.external_validator = external_validator or ExternalLicenseValidator()

    def list_keys(self):
        return self.key_repository.get_all()

    def revoke_key(self, key_code):
        key_code = str(key_code or "").strip().upper()
        product_key = self.key_repository.get_by_code(key_code)
        if not product_key:
            raise ValueError("Product key not found")

        return self.key_repository.revoke(product_key)

    def start_trial(self, device_id, device_name=None, fingerprint=None, public_ip=None):
        fingerprint = fingerprint or {}
        fingerprint_hash = fingerprint.get("fingerprint_hash")
        trial = self.trial_repository.get_by_device(device_id)
        if not trial and fingerprint_hash:
            trial = self.trial_repository.get_by_fingerprint(fingerprint_hash)
        if trial:
            return trial

        now = datetime.utcnow()
        trial = self.trial_repository.create(
            TrialSession(
                device_id=device_id,
                started_at=now,
                expires_at=now + timedelta(days=7),
                device_fingerprint_hash=fingerprint_hash,
                machine_guid_hash=fingerprint.get("machine_guid_hash"),
                disk_serial_hash=fingerprint.get("disk_serial_hash"),
                public_ip_history=[public_ip] if public_ip else [],
                fingerprint=fingerprint,
            )
        )
        AuditService.log("trial.started", category="license", success=True, metadata={"device_id": device_id, "fingerprint_hash": fingerprint_hash})
        return trial

    def get_status(self, device_id, fingerprint=None):
        activation = self.activation_repository.get_by_device(device_id)
        now = datetime.utcnow()
        fingerprint = fingerprint or {}
        activation_fingerprint = getattr(activation, "device_fingerprint_hash", None) if activation else None
        request_fingerprint = fingerprint.get("fingerprint_hash")

        if activation and activation_fingerprint and request_fingerprint and activation_fingerprint != request_fingerprint:
            AuditService.log(
                "license.fingerprint_changed",
                category="license",
                success=False,
                reason="Fingerprint hash mismatch",
                metadata={"device_id": device_id},
            )
            return {
                "status": "DEVICE_CHANGED",
                "expires_at": activation.expires_at,
                "days_remaining": 0,
                "plan_name": activation.product_key.plan_name if activation.product_key else None,
            }

        if (
            activation
            and activation.expires_at > now
            and not getattr(activation, "revoked_at", None)
            and activation.product_key
            and not activation.product_key.is_revoked
        ):
            return {
                "status": "LICENSED",
                "expires_at": activation.expires_at,
                "days_remaining": max(
                    1,
                    ceil((activation.expires_at - now).total_seconds() / 86400),
                ),
                "plan_name": activation.product_key.plan_name,
                "license_token": self._signed_token(activation, activation.product_key),
            }

        trial = self.trial_repository.get_by_device(device_id)
        if not trial:
            return {
                "status": "NOT_FOUND"
            }

        if trial.expires_at > now:
            return {
                "status": "TRIAL_ACTIVE",
                "expires_at": trial.expires_at,
                "days_remaining": max(
                    1,
                    ceil((trial.expires_at - now).total_seconds() / 86400),
                ),
            }

        if trial.is_held:
            return {
                "status": "HELD",
                "expires_at": trial.expires_at,
                "days_remaining": 0
            }

        return {
            "status": "TRIAL_EXPIRED",
            "expires_at": trial.expires_at,
            "days_remaining": 0
        }

    def activate(self, key_code, device_id, device_name=None, fingerprint=None):
        key_code = str(key_code or "").strip().upper()
        if not key_code:
            raise ValueError("Product key is required")
        fingerprint = fingerprint or {}
        product_key = self.key_repository.get_by_code(key_code)
        external_expiry = None
        if not product_key or getattr(product_key, "source", None) == "external":
            validation = self.external_validator.validate(key_code)
            external_expiry = validation.expires_at
            if not product_key:
                remaining_days = max(
                    1,
                    ceil((external_expiry - datetime.utcnow()).total_seconds() / 86400),
                )
                candidate = ProductKey(
                    key_code=key_code,
                    plan_name="LR",
                    max_activations=1,
                    valid_days=remaining_days,
                    issued_to=device_name,
                    source="external",
                    external_expires_at=external_expiry,
                )
                try:
                    product_key = self.key_repository.create(candidate)
                except Exception:
                    # A concurrent activation may have imported the same unique key.
                    product_key = self.key_repository.get_by_code(key_code)
                    if not product_key:
                        raise

        if not product_key or product_key.is_revoked:
            AuditService.log("license.activation_failed", category="license", success=False, reason="Invalid product key", metadata={"device_id": device_id})
            raise ValueError("Invalid product key")

        existing_activation = self.activation_repository.get_active_for_key(
            product_key.id
        )
        now = datetime.utcnow()

        if existing_activation:
            if existing_activation.device_id == device_id:
                if external_expiry and existing_activation.expires_at != external_expiry:
                    existing_activation = self.activation_repository.update_expiry(
                        existing_activation, external_expiry
                    )
                return self._activation_response(existing_activation, product_key, device_id)

            transfer_allowed_at = existing_activation.activated_at + timedelta(days=KEY_TRANSFER_LOCK_DAYS)
            if now < transfer_allowed_at:
                remaining_days = max(1, (transfer_allowed_at - now).days + 1)
                raise ValueError(
                    "This product key is already assigned to another VM. "
                    f"It can be moved after {transfer_allowed_at.date()} "
                    f"({remaining_days} day(s) remaining)."
                )

            self.activation_repository.deactivate_for_key(product_key.id, now)

        try:
            activation = self.activation_repository.create(
                LicenseActivation(
                    product_key_id=product_key.id,
                    device_id=device_id,
                    device_name=device_name,
                    activated_at=now,
                    expires_at=external_expiry or now + timedelta(days=product_key.valid_days),
                    device_fingerprint_hash=fingerprint.get("fingerprint_hash"),
                    fingerprint=fingerprint,
                )
            )
        except DuplicateKeyError as error:
            # The database unique index is the final guard when two servers
            # try the same key concurrently. Same-device retries are safe.
            winner = self.activation_repository.get_active_for_key(product_key.id)
            if winner and winner.device_id == device_id:
                activation = winner
            else:
                raise ValueError(
                    "This product key is already assigned to another VM."
                ) from error
        AuditService.log("license.activated", category="license", success=True, metadata={"device_id": device_id, "product_key_id": str(product_key.id)})

        return self._activation_response(activation, product_key, device_id)

    def _activation_response(self, activation, product_key, device_id):
        trial = self.trial_repository.get_by_device(device_id)

        return {
            "status": "LICENSED",
            "plan_name": product_key.plan_name,
            "expires_at": activation.expires_at,
            "device_id": activation.device_id,
            "license_token": self._signed_token(activation, product_key),
            "transfer_locked_until": (
                activation.activated_at + timedelta(days=KEY_TRANSFER_LOCK_DAYS)
            ),
            "resume_context": trial.held_context if trial else None
        }

    def hold(self, device_id, context=None, fingerprint=None):
        fingerprint = fingerprint or {}
        trial = self.trial_repository.get_by_device(device_id)
        if not trial:
            now = datetime.utcnow()
            trial = self.trial_repository.create(
                TrialSession(
                    device_id=device_id,
                    started_at=now,
                    expires_at=now,
                    is_held=True,
                    held_at=now,
                    held_context=context,
                    device_fingerprint_hash=fingerprint.get("fingerprint_hash"),
                    machine_guid_hash=fingerprint.get("machine_guid_hash"),
                    disk_serial_hash=fingerprint.get("disk_serial_hash"),
                    fingerprint=fingerprint,
                )
            )
            return trial

        trial.is_held = True
        trial.held_at = datetime.utcnow()
        trial.held_context = context

        return self.trial_repository.update(trial)

    def _signed_token(self, activation, product_key):
        return sign_license_token({
            "device_id": activation.device_id,
            "activation_id": str(activation.id),
            "license_id": str(product_key.id),
            "plan": product_key.plan_name,
            "features": self._features_for_plan(product_key.plan_name),
            "issued_at": datetime.utcnow(),
            "expires_at": activation.expires_at,
            "revoked": False,
            "fingerprint_hash": getattr(activation, "device_fingerprint_hash", None),
        })

    def _features_for_plan(self, plan_name):
        return {
            "STANDARD": ["remote", "admin", "monitor"],
            "TRIAL": ["remote", "monitor"],
        }.get(str(plan_name or "").upper(), ["remote"])
