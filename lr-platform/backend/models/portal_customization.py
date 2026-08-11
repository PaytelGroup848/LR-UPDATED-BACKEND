from copy import deepcopy
from datetime import datetime

from backend.extensions import db
from backend.tenancy.context import as_object_id, scoped_filter, tenant_document


DEFAULT_PORTAL_CONFIG = {
    "company_name": "LR Remote Access",
    "portal_title": "LR Remote Access",
    "browser_title": "LR Remote Access",
    "primary_color": "#159a35",
    "secondary_color": "#0b2028",
    "accent_color": "#16a34a",
    "background_color": "#f7f9fa",
    "background_overlay_opacity": 0.0,
    "welcome_heading": "Welcome to LR Remote Access",
    "welcome_description": "Sign in to access your remote desktop and applications.",
    "username_label": "Username",
    "password_label": "Password",
    "login_button_text": "Login",
    "login_card_position": "center",
    "login_card_width": 420,
    "login_card_opacity": 1.0,
    "login_card_border_radius": 12,
    "show_company_code": True,
    "show_remember_me": True,
    "show_forgot_password": False,
    "show_logo": True,
    "show_welcome_text": True,
    "header_text": "",
    "footer_text": "",
    "copyright_text": "LR Remote Access. All rights reserved.",
    "support_email": "",
    "support_url": "",
    "privacy_url": "",
    "terms_url": "",
    "show_header": False,
    "show_footer": True,
    "default_connection_mode": "web",
    "remember_connection_preference": True,
    "show_available_applications_after_login": True,
    "logo_asset": None,
    "favicon_asset": None,
    "background_image_asset": None,
}


def default_portal_config():
    return deepcopy(DEFAULT_PORTAL_CONFIG)


class PortalCustomization:
    collection = db["portal_customizations"]
    STATES = ("draft", "published")

    @classmethod
    def get(cls, tenant_id, state):
        if state not in cls.STATES:
            raise ValueError("Invalid portal configuration state")
        return cls.collection.find_one(
            scoped_filter(tenant_id, {"state": state})
        )

    @classmethod
    def save_draft(cls, tenant_id, config, updated_by=None):
        tenant_id = as_object_id(tenant_id)
        now = datetime.utcnow()
        query = scoped_filter(tenant_id, {"state": "draft"})
        existing = cls.collection.find_one(query) or {}
        version = max(int(existing.get("version") or 0), 0) + 1
        document = tenant_document(tenant_id, {
            "state": "draft",
            "config": deepcopy(config),
            "version": version,
            "updated_at": now,
            "updated_by": str(updated_by or "") or None,
        })
        cls.collection.update_one(
            query,
            {
                "$set": document,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        return cls.collection.find_one(query) or {
            **document,
            "created_at": now,
        }

    @classmethod
    def publish(cls, tenant_id, config, published_by=None):
        tenant_id = as_object_id(tenant_id)
        now = datetime.utcnow()
        query = scoped_filter(tenant_id, {"state": "published"})
        existing = cls.collection.find_one(query) or {}
        version = max(int(existing.get("version") or 0), 0) + 1
        document = tenant_document(tenant_id, {
            "state": "published",
            "config": deepcopy(config),
            "version": version,
            "updated_at": now,
            "updated_by": str(published_by or "") or None,
            "published_at": now,
            "published_by": str(published_by or "") or None,
        })
        cls.collection.update_one(
            query,
            {
                "$set": document,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        return cls.collection.find_one(query) or {
            **document,
            "created_at": now,
        }

    @staticmethod
    def to_dict(document):
        if not document:
            return None
        return {
            "id": str(document.get("_id")) if document.get("_id") else None,
            "tenant_id": str(document.get("tenant_id")) if document.get("tenant_id") else None,
            "state": document.get("state"),
            "config": deepcopy(document.get("config") or {}),
            "version": int(document.get("version") or 0),
            "created_at": (
                document.get("created_at").isoformat()
                if document.get("created_at")
                else None
            ),
            "updated_at": (
                document.get("updated_at").isoformat()
                if document.get("updated_at")
                else None
            ),
            "published_at": (
                document.get("published_at").isoformat()
                if document.get("published_at")
                else None
            ),
            "updated_by": document.get("updated_by"),
            "published_by": document.get("published_by"),
        }
