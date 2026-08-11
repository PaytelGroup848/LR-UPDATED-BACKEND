from datetime import datetime
from datetime import timedelta
from datetime import timezone

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from backend.extensions import db
from backend.models.license import TrialSession
from backend.models.user import User
from backend.repositories.license_repository import LicenseActivationRepository
from backend.repositories.license_repository import ProductKeyRepository
from backend.repositories.license_repository import TrialSessionRepository
from backend.services.license_service import LicenseService


TRIAL_DAYS = 7
BLOCKED_STATES = {"TRIAL_EXPIRED", "HELD", "NOT_FOUND", "DEVICE_CHANGED"}


def _utc_naive(value):
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _parse_datetime(value):
    if isinstance(value, datetime):
        return _utc_naive(value)
    if isinstance(value, str):
        try:
            return _utc_naive(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _created_at_for_user(user):
    created_at = _parse_datetime((user or {}).get("created_at"))
    if created_at:
        return created_at

    user_id = (user or {}).get("_id")
    if isinstance(user_id, ObjectId):
        return _utc_naive(user_id.generation_time)

    try:
        return _utc_naive(ObjectId(str(user_id)).generation_time)
    except Exception:
        return datetime.utcnow()


def _serialize_datetime(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _license_service():
    return LicenseService(
        key_repository=ProductKeyRepository(db),
        activation_repository=LicenseActivationRepository(db),
        trial_repository=TrialSessionRepository(db),
    )


class UserLicenseService:
    @staticmethod
    def identity_for_user(user):
        return f"user:{User.get_id(user)}"

    @staticmethod
    def is_bypass_user(user):
        return User.has_role(user, "Admin")

    @staticmethod
    def ensure_trial(user):
        if not user or UserLicenseService.is_bypass_user(user):
            return None

        identity = UserLicenseService.identity_for_user(user)
        service = _license_service()
        trial = service.trial_repository.get_by_device(identity)
        if trial:
            return trial

        started_at = _created_at_for_user(user)
        try:
            return service.trial_repository.create(
                TrialSession(
                    device_id=identity,
                    started_at=started_at,
                    expires_at=started_at + timedelta(days=TRIAL_DAYS),
                )
            )
        except DuplicateKeyError:
            return service.trial_repository.get_by_device(identity)

    @staticmethod
    def get_status(user):
        if not user:
            return {"status": "NOT_FOUND", "blocked": True}

        if UserLicenseService.is_bypass_user(user):
            return {
                "status": "LICENSED",
                "blocked": False,
                "plan_name": "ADMIN",
                "days_remaining": None,
                "bypass": True,
            }

        UserLicenseService.ensure_trial(user)
        service = _license_service()
        status = service.get_status(UserLicenseService.identity_for_user(user))
        state = status.get("status")
        blocked = state in BLOCKED_STATES
        status.update({
            "blocked": blocked,
            "trial_days": TRIAL_DAYS,
            "user_id": User.get_id(user),
            "username": user.get("username"),
            "created_at": _serialize_datetime(_created_at_for_user(user)),
            "expires_at": _serialize_datetime(status.get("expires_at")),
        })
        if blocked:
            status["message"] = "Your license is not active. Contact your administrator."
        return status

    @staticmethod
    def is_blocked(user):
        return UserLicenseService.get_status(user).get("blocked") is True

    @staticmethod
    def block_response(user, context=None):
        status = UserLicenseService.get_status(user)
        if status.get("blocked"):
            UserLicenseService.hold(user, context=context)
            status = UserLicenseService.get_status(user)
            return {
                "success": False,
                "license_required": True,
                "message": "Your license is not active. Contact your administrator.",
                "error": "License not active",
                "license": status,
            }, 402
        return None

    @staticmethod
    def activate(user, key_code):
        if not user:
            raise ValueError("User not found")
        if not key_code:
            raise ValueError("Product key is required")

        UserLicenseService.ensure_trial(user)
        result = _license_service().activate(
            key_code=key_code,
            device_id=UserLicenseService.identity_for_user(user),
            device_name=user.get("username"),
        )
        result["expires_at"] = _serialize_datetime(result.get("expires_at"))
        result["transfer_locked_until"] = _serialize_datetime(
            result.get("transfer_locked_until")
        )
        return result

    @staticmethod
    def hold(user, context=None):
        if not user or UserLicenseService.is_bypass_user(user):
            return None
        UserLicenseService.ensure_trial(user)
        return _license_service().hold(
            device_id=UserLicenseService.identity_for_user(user),
            context=context,
        )
