import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from backend.core.config import settings


PREFIX = "enc:v1:"


def _fernet():
    secret = settings.CREDENTIAL_ENCRYPTION_KEY or settings.SECRET_KEY
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value):
    if value in (None, ""):
        return None

    text = str(value)
    if text.startswith(PREFIX):
        return text

    token = _fernet().encrypt(text.encode("utf-8")).decode("utf-8")
    return f"{PREFIX}{token}"


def decrypt_secret(value):
    if value in (None, ""):
        return ""

    text = str(value)
    if not text.startswith(PREFIX):
        return text

    token = text[len(PREFIX):]
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        return ""
