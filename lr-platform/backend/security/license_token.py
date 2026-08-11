import base64
import json
import os
from datetime import datetime, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization


DEV_PRIVATE_KEY_B64 = "ZDHvUL5eT8_ehYwVrwIupZRhrcdMnPOBOkq0UyDxFsI="


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True, default=_json_default).encode("utf-8")


def _json_default(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    raise TypeError(f"{type(value)!r} is not JSON serializable")


def _private_key():
    configured = os.getenv("LICENSE_SIGNING_PRIVATE_KEY_B64") or DEV_PRIVATE_KEY_B64
    raw = base64.urlsafe_b64decode(configured + "=" * (-len(configured) % 4))
    return Ed25519PrivateKey.from_private_bytes(raw)


def public_key_b64() -> str:
    public_key = _private_key().public_key()
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.urlsafe_b64encode(raw).decode("ascii")


def sign_license_token(claims: dict) -> str:
    header = {"alg": "EdDSA", "typ": "LR-LICENSE", "kid": "lr-license-v1"}
    header_b64 = _b64url(_json_bytes(header))
    payload_b64 = _b64url(_json_bytes(claims))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = _private_key().sign(signing_input)
    return f"{header_b64}.{payload_b64}.{_b64url(signature)}"
