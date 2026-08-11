from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Mapping

from bson import ObjectId


class TenantScopeError(ValueError):
    """Raised when a tenant-owned operation has no valid tenant context."""


_tenant_context: ContextVar[ObjectId | None] = ContextVar("tenant_id", default=None)


def as_object_id(value: Any, *, field: str = "tenant_id") -> ObjectId:
    if isinstance(value, ObjectId):
        return value
    try:
        return ObjectId(str(value))
    except Exception as exc:
        raise TenantScopeError(f"Invalid {field}") from exc


def optional_object_id(value: Any) -> ObjectId | None:
    if value in (None, ""):
        return None
    return as_object_id(value)


def tenant_id_from_user(user: Any, *, required: bool = True) -> ObjectId | None:
    if user is None:
        value = None
    elif isinstance(user, Mapping):
        value = user.get("tenant_id")
    else:
        value = getattr(user, "tenant_id", None)
    if value in (None, ""):
        if required:
            raise TenantScopeError("Authenticated user is not assigned to a tenant")
        return None
    return as_object_id(value)


def set_current_tenant(tenant_id: Any):
    return _tenant_context.set(as_object_id(tenant_id))


def reset_current_tenant(token) -> None:
    _tenant_context.reset(token)


def current_tenant_id(*, required: bool = True) -> ObjectId | None:
    tenant_id = _tenant_context.get()
    if tenant_id is None and required:
        raise TenantScopeError("Tenant context is required")
    return tenant_id


def scoped_filter(tenant_id: Any, query: Mapping[str, Any] | None = None) -> dict:
    """Return a tenant-pinned Mongo filter; caller filters cannot override it."""
    tenant_object_id = as_object_id(tenant_id)
    result = dict(query or {})
    supplied = result.pop("tenant_id", None)
    if supplied not in (None, "") and as_object_id(supplied) != tenant_object_id:
        raise TenantScopeError("Cross-tenant query rejected")
    result["tenant_id"] = tenant_object_id
    return result


def tenant_document(tenant_id: Any, values: Mapping[str, Any] | None = None) -> dict:
    result = dict(values or {})
    supplied = result.pop("tenant_id", None)
    tenant_object_id = as_object_id(tenant_id)
    if supplied not in (None, "") and as_object_id(supplied) != tenant_object_id:
        raise TenantScopeError("Cross-tenant document rejected")
    result["tenant_id"] = tenant_object_id
    return result
