import re
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

from backend.core.config_paths import INSTANCE_DIR
from backend.models.portal_customization import (
    PortalCustomization,
    default_portal_config,
)
from backend.models.tenant import Tenant
from backend.services.audit_service import AuditService
from backend.tenancy.context import as_object_id, tenant_id_from_user


class PortalCustomizationError(ValueError):
    def __init__(self, message, *, status_code=400, code="invalid_portal_settings"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


TEXT_LIMITS = {
    "company_name": 120,
    "portal_title": 120,
    "browser_title": 120,
    "welcome_heading": 160,
    "welcome_description": 600,
    "username_label": 60,
    "password_label": 60,
    "login_button_text": 60,
    "header_text": 300,
    "footer_text": 600,
    "copyright_text": 300,
    "support_email": 254,
}
COLOR_FIELDS = {
    "primary_color",
    "secondary_color",
    "accent_color",
    "background_color",
}
URL_FIELDS = {
    "support_url",
    "privacy_url",
    "terms_url",
}
BOOLEAN_FIELDS = {
    "show_company_code",
    "show_remember_me",
    "show_forgot_password",
    "show_logo",
    "show_welcome_text",
    "show_header",
    "show_footer",
    "remember_connection_preference",
    "show_available_applications_after_login",
}
ASSET_FIELDS = {
    "logo_asset",
    "favicon_asset",
    "background_image_asset",
}
EDITABLE_FIELDS = (
    set(TEXT_LIMITS)
    | COLOR_FIELDS
    | URL_FIELDS
    | BOOLEAN_FIELDS
    | {
        "background_overlay_opacity",
        "login_card_position",
        "login_card_width",
        "login_card_opacity",
        "login_card_border_radius",
        "default_connection_mode",
    }
)

ASSET_RULES = {
    "logo": {
        "field": "logo_asset",
        "limit": 2 * 1024 * 1024,
        "extensions": {"png", "jpg", "jpeg", "webp"},
    },
    "favicon": {
        "field": "favicon_asset",
        "limit": 512 * 1024,
        "extensions": {"png", "ico"},
    },
    "background": {
        "field": "background_image_asset",
        "limit": 5 * 1024 * 1024,
        "extensions": {"png", "jpg", "jpeg", "webp"},
    },
}
MIME_BY_EXTENSION = {
    "png": {"image/png"},
    "jpg": {"image/jpeg"},
    "jpeg": {"image/jpeg"},
    "webp": {"image/webp"},
    "ico": {"image/x-icon", "image/vnd.microsoft.icon"},
}


def _safe_text(field, value):
    text = str(value or "").strip()
    if len(text) > TEXT_LIMITS[field]:
        raise PortalCustomizationError(
            f"{field} must be at most {TEXT_LIMITS[field]} characters"
        )
    if any(character in text for character in ("\x00", "<", ">")):
        raise PortalCustomizationError(f"{field} contains unsupported characters")
    return text


def _safe_bool(field, value):
    if isinstance(value, bool):
        result = value
    elif str(value).strip().lower() in {"1", "true", "yes", "on"}:
        result = True
    elif str(value).strip().lower() in {"0", "false", "no", "off"}:
        result = False
    else:
        raise PortalCustomizationError(f"{field} must be true or false")
    if field == "show_forgot_password" and result:
        raise PortalCustomizationError(
            "Forgot Password cannot be enabled because it is not supported by the current login flow"
        )
    return result


def _safe_url(field, value):
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > 500:
        raise PortalCustomizationError(f"{field} is too long")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PortalCustomizationError(f"{field} must be a valid HTTP or HTTPS URL")
    return text


def _safe_email(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > TEXT_LIMITS["support_email"]:
        raise PortalCustomizationError("support_email is too long")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", text):
        raise PortalCustomizationError("support_email must be a valid email address")
    return text


def _safe_number(field, value, minimum, maximum, *, integer=False):
    try:
        number = int(value) if integer else float(value)
    except (TypeError, ValueError) as error:
        raise PortalCustomizationError(f"{field} must be a number") from error
    if number < minimum or number > maximum:
        raise PortalCustomizationError(
            f"{field} must be between {minimum} and {maximum}"
        )
    return number


def validate_portal_updates(payload):
    if not isinstance(payload, dict):
        raise PortalCustomizationError("Portal settings must be a JSON object")
    unknown = sorted(set(payload) - EDITABLE_FIELDS)
    if unknown:
        raise PortalCustomizationError(
            f"Unsupported portal setting: {unknown[0]}"
        )

    cleaned = {}
    for field, value in payload.items():
        if field in TEXT_LIMITS:
            cleaned[field] = _safe_email(value) if field == "support_email" else _safe_text(field, value)
        elif field in COLOR_FIELDS:
            color = str(value or "").strip().lower()
            if not re.fullmatch(r"#[0-9a-f]{6}", color):
                raise PortalCustomizationError(f"{field} must be a 6-digit hex colour")
            cleaned[field] = color
        elif field in URL_FIELDS:
            cleaned[field] = _safe_url(field, value)
        elif field in BOOLEAN_FIELDS:
            cleaned[field] = _safe_bool(field, value)
        elif field == "background_overlay_opacity":
            cleaned[field] = _safe_number(field, value, 0, 1)
        elif field == "login_card_opacity":
            cleaned[field] = _safe_number(field, value, 0.3, 1)
        elif field == "login_card_width":
            cleaned[field] = _safe_number(field, value, 280, 720, integer=True)
        elif field == "login_card_border_radius":
            cleaned[field] = _safe_number(field, value, 0, 48, integer=True)
        elif field == "login_card_position":
            position = str(value or "").strip().lower()
            if position not in {"left", "center", "right"}:
                raise PortalCustomizationError(
                    "login_card_position must be left, center, or right"
                )
            cleaned[field] = position
        elif field == "default_connection_mode":
            mode = str(value or "").strip().lower()
            if mode not in {"web", "remoteapp", "desktop"}:
                raise PortalCustomizationError(
                    "default_connection_mode must be web, remoteapp, or desktop"
                )
            cleaned[field] = mode
    return cleaned


def _detected_extension(content):
    if (
        len(content) >= 33
        and content.startswith(b"\x89PNG\r\n\x1a\n")
        and content[12:16] == b"IHDR"
        and int.from_bytes(content[16:20], "big") > 0
        and int.from_bytes(content[20:24], "big") > 0
        and b"IEND" in content[-24:]
    ):
        return "png"
    if content.startswith(b"\xff\xd8\xff") and content.endswith(b"\xff\xd9"):
        return "jpg"
    if (
        len(content) >= 20
        and content[:4] == b"RIFF"
        and content[8:12] == b"WEBP"
        and content[12:16] in {b"VP8 ", b"VP8L", b"VP8X"}
        and int.from_bytes(content[4:8], "little") + 8 <= len(content)
    ):
        return "webp"
    if (
        len(content) >= 22
        and content.startswith(b"\x00\x00\x01\x00")
        and int.from_bytes(content[4:6], "little") > 0
    ):
        return "ico"
    return None


class PortalCustomizationService:
    storage_root = Path(INSTANCE_DIR) / "portal_customization_assets"

    @classmethod
    def _tenant_id(cls, actor):
        try:
            return tenant_id_from_user(actor)
        except Exception as error:
            raise PortalCustomizationError(
                "Authenticated administrator is not assigned to a company",
                status_code=423,
                code="tenant_required",
            ) from error

    @classmethod
    def _config_with_defaults(cls, document):
        config = default_portal_config()
        if document:
            config.update(deepcopy(document.get("config") or {}))
        return config

    @staticmethod
    def _asset_url(tenant_reference, filename, *, public):
        if not filename:
            return None
        if public:
            return f"/api/public/portal-customization/assets/{tenant_reference}/{filename}"
        return f"/api/admin/portal-customization/assets/{filename}"

    @classmethod
    def _external_config(cls, config, tenant_reference, *, public):
        result = deepcopy(config)
        asset_map = {
            "logo_asset": "logo_url",
            "favicon_asset": "favicon_url",
            "background_image_asset": "background_image_url",
        }
        for internal_field, public_field in asset_map.items():
            filename = result.pop(internal_field, None)
            result[public_field] = cls._asset_url(
                tenant_reference,
                filename,
                public=public,
            )
        return result

    @classmethod
    def _admin_document(cls, document, tenant_id, state):
        persisted = bool(document)
        raw = PortalCustomization.to_dict(document) if document else {
            "id": None,
            "tenant_id": str(tenant_id),
            "state": state,
            "version": 0,
            "created_at": None,
            "updated_at": None,
            "published_at": None,
            "updated_by": None,
            "published_by": None,
        }
        raw["config"] = cls._external_config(
            cls._config_with_defaults(document),
            tenant_id,
            public=False,
        )
        raw["persisted"] = persisted
        raw["is_default"] = not persisted
        return raw

    @classmethod
    def get_draft(cls, actor):
        tenant_id = cls._tenant_id(actor)
        draft = PortalCustomization.get(tenant_id, "draft")
        published = PortalCustomization.get(tenant_id, "published")
        return {
            "success": True,
            "settings": cls._admin_document(draft, tenant_id, "draft"),
            "published": (
                {
                    "version": int(published.get("version") or 0),
                    "published_at": (
                        published.get("published_at").isoformat()
                        if published.get("published_at")
                        else None
                    ),
                }
                if published
                else None
            ),
        }

    @classmethod
    def save_draft(cls, actor, payload, ip_address=None):
        tenant_id = cls._tenant_id(actor)
        try:
            updates = validate_portal_updates(payload)
        except PortalCustomizationError as error:
            AuditService.log(
                "portal_customization.validation_failed",
                user=actor,
                category="portal_customization",
                ip_address=ip_address,
                success=False,
                reason=str(error),
            )
            raise
        current = PortalCustomization.get(tenant_id, "draft")
        config = cls._config_with_defaults(current)
        config.update(updates)
        document = PortalCustomization.save_draft(
            tenant_id,
            config,
            updated_by=getattr(actor, "id", None),
        )
        AuditService.log(
            "portal_customization.draft_saved",
            user=actor,
            category="portal_customization",
            ip_address=ip_address,
            metadata={
                "version": int(document.get("version") or 0),
                "fields": sorted(updates),
            },
        )
        return {
            "success": True,
            "message": "Portal customization draft saved",
            "settings": cls._admin_document(document, tenant_id, "draft"),
        }

    @classmethod
    def publish(cls, actor, ip_address=None):
        tenant_id = cls._tenant_id(actor)
        draft = PortalCustomization.get(tenant_id, "draft")
        config = cls._config_with_defaults(draft)
        try:
            validated = default_portal_config()
            validated.update(
                validate_portal_updates({
                    key: value
                    for key, value in config.items()
                    if key in EDITABLE_FIELDS
                })
            )
            for field in ASSET_FIELDS:
                filename = config.get(field)
                if filename:
                    cls._validate_stored_asset_name(filename)
                    if not cls._asset_file(tenant_id, filename).is_file():
                        raise PortalCustomizationError(
                            f"The configured {field.replace('_asset', '')} file is missing"
                        )
                    validated[field] = filename
        except PortalCustomizationError as error:
            AuditService.log(
                "portal_customization.publish_failed",
                user=actor,
                category="portal_customization",
                ip_address=ip_address,
                success=False,
                reason=str(error),
            )
            raise

        document = PortalCustomization.publish(
            tenant_id,
            validated,
            published_by=getattr(actor, "id", None),
        )
        AuditService.log(
            "portal_customization.published",
            user=actor,
            category="portal_customization",
            ip_address=ip_address,
            metadata={"version": int(document.get("version") or 0)},
        )
        return {
            "success": True,
            "message": "Portal customization published",
            "settings": cls._admin_document(document, tenant_id, "published"),
        }

    @classmethod
    def reset_draft(cls, actor, ip_address=None):
        tenant_id = cls._tenant_id(actor)
        old_draft = PortalCustomization.get(tenant_id, "draft")
        old_assets = {
            (old_draft.get("config") or {}).get(field)
            for field in ASSET_FIELDS
        } if old_draft else set()
        document = PortalCustomization.save_draft(
            tenant_id,
            default_portal_config(),
            updated_by=getattr(actor, "id", None),
        )
        for filename in old_assets:
            cls._delete_if_unreferenced(tenant_id, filename)
        AuditService.log(
            "portal_customization.draft_reset",
            user=actor,
            category="portal_customization",
            ip_address=ip_address,
            metadata={"version": int(document.get("version") or 0)},
        )
        return {
            "success": True,
            "message": "Draft reset to LR defaults; published portal was not changed",
            "settings": cls._admin_document(document, tenant_id, "draft"),
        }

    @classmethod
    def public_settings(cls, company_code):
        tenant = Tenant.get_by_code(company_code) if str(company_code or "").strip() else None
        tenant_active = bool(tenant and tenant.get("is_active"))
        published = (
            PortalCustomization.get(tenant["_id"], "published")
            if tenant_active
            else None
        )
        public_reference = (
            tenant.get("company_code") or tenant.get("company_slug")
            if tenant_active
            else "default"
        )
        config = cls._config_with_defaults(published)
        return {
            "success": True,
            "company_resolved": tenant_active,
            "published": bool(published),
            "version": int((published or {}).get("version") or 0),
            "published_at": (
                published.get("published_at").isoformat()
                if published and published.get("published_at")
                else None
            ),
            "config": cls._external_config(
                config,
                public_reference,
                public=True,
            ),
        }

    @classmethod
    def upload_asset(cls, actor, asset_type, uploaded_file, ip_address=None):
        tenant_id = cls._tenant_id(actor)
        rule = ASSET_RULES.get(str(asset_type or "").lower())
        if not rule:
            raise PortalCustomizationError("Unsupported portal asset type")
        try:
            filename = str(getattr(uploaded_file, "filename", "") or "")
            if not uploaded_file or not filename:
                raise PortalCustomizationError("Image file is required")
            extension = Path(filename).suffix.lower().lstrip(".")
            if extension not in rule["extensions"]:
                raise PortalCustomizationError(
                    f"{asset_type} must use one of: {', '.join(sorted(rule['extensions']))}"
                )
            mimetype = str(getattr(uploaded_file, "mimetype", "") or "").lower()
            if mimetype not in MIME_BY_EXTENSION.get(extension, set()):
                raise PortalCustomizationError("Image MIME type does not match its extension")
            content = uploaded_file.stream.read(rule["limit"] + 1)
            if len(content) > rule["limit"]:
                raise PortalCustomizationError(
                    f"{asset_type} image is larger than the allowed limit"
                )
            detected = _detected_extension(content)
            expected = "jpg" if extension in {"jpg", "jpeg"} else extension
            if detected != expected:
                raise PortalCustomizationError("Image file signature is invalid")
        except PortalCustomizationError as error:
            AuditService.log(
                "portal_customization.upload_failed",
                user=actor,
                category="portal_customization",
                ip_address=ip_address,
                success=False,
                reason=str(error),
                metadata={"asset_type": asset_type},
            )
            raise

        tenant_directory = cls.storage_root / str(tenant_id)
        tenant_directory.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid4().hex}.{detected}"
        destination = tenant_directory / stored_name
        destination.write_bytes(content)

        current = PortalCustomization.get(tenant_id, "draft")
        config = cls._config_with_defaults(current)
        old_filename = config.get(rule["field"])
        config[rule["field"]] = stored_name
        document = PortalCustomization.save_draft(
            tenant_id,
            config,
            updated_by=getattr(actor, "id", None),
        )
        cls._delete_if_unreferenced(tenant_id, old_filename)
        AuditService.log(
            "portal_customization.asset_uploaded",
            user=actor,
            category="portal_customization",
            ip_address=ip_address,
            metadata={
                "asset_type": asset_type,
                "version": int(document.get("version") or 0),
            },
        )
        return {
            "success": True,
            "message": f"{asset_type.title()} uploaded",
            "settings": cls._admin_document(document, tenant_id, "draft"),
        }

    @classmethod
    def admin_asset_path(cls, actor, filename):
        tenant_id = cls._tenant_id(actor)
        cls._validate_stored_asset_name(filename)
        references = set()
        for state in PortalCustomization.STATES:
            document = PortalCustomization.get(tenant_id, state)
            if document:
                references.update(
                    (document.get("config") or {}).get(field)
                    for field in ASSET_FIELDS
                )
        if filename not in references:
            raise PortalCustomizationError(
                "Portal asset not found",
                status_code=404,
                code="portal_asset_not_found",
            )
        path = cls._asset_file(tenant_id, filename)
        if not path.is_file():
            raise PortalCustomizationError(
                "Portal asset not found",
                status_code=404,
                code="portal_asset_not_found",
            )
        return path

    @classmethod
    def public_asset_path(cls, company_code, filename):
        tenant = Tenant.get_by_code(company_code)
        if not tenant or not tenant.get("is_active"):
            raise PortalCustomizationError(
                "Portal asset not found",
                status_code=404,
                code="portal_asset_not_found",
            )
        tenant_id = as_object_id(tenant.get("_id"))
        cls._validate_stored_asset_name(filename)
        published = PortalCustomization.get(tenant_id, "published")
        references = {
            (published.get("config") or {}).get(field)
            for field in ASSET_FIELDS
        } if published else set()
        if filename not in references:
            raise PortalCustomizationError(
                "Portal asset not found",
                status_code=404,
                code="portal_asset_not_found",
            )
        path = cls._asset_file(tenant_id, filename)
        if not path.is_file():
            raise PortalCustomizationError(
                "Portal asset not found",
                status_code=404,
                code="portal_asset_not_found",
            )
        return path

    @classmethod
    def _asset_file(cls, tenant_id, filename):
        cls._validate_stored_asset_name(filename)
        return cls.storage_root / str(as_object_id(tenant_id)) / filename

    @staticmethod
    def _validate_stored_asset_name(filename):
        if not re.fullmatch(r"[0-9a-f]{32}\.(png|jpg|webp|ico)", str(filename or "")):
            raise PortalCustomizationError(
                "Invalid portal asset name",
                status_code=404,
                code="portal_asset_not_found",
            )

    @classmethod
    def _delete_if_unreferenced(cls, tenant_id, filename):
        if not filename:
            return
        try:
            cls._validate_stored_asset_name(filename)
        except PortalCustomizationError:
            return
        for state in PortalCustomization.STATES:
            document = PortalCustomization.get(tenant_id, state)
            if document and filename in {
                (document.get("config") or {}).get(field)
                for field in ASSET_FIELDS
            }:
                return
        try:
            cls._asset_file(tenant_id, filename).unlink(missing_ok=True)
        except OSError:
            pass
