import secrets
import string


_ALPHABET = string.ascii_uppercase + string.digits

_GROUP_SIZE = 5

_GROUP_COUNT = 4

_SAFE_ALPHABET = "".join(
    ch for ch in _ALPHABET if ch not in "01OI"
)


def generate_product_key(prefix: str = "LR") -> str:

    groups = [
        "".join(
            secrets.choice(_SAFE_ALPHABET)
            for _ in range(_GROUP_SIZE)
        )
        for _ in range(_GROUP_COUNT)
    ]

    return f"{prefix}-" + "-".join(groups)


def generate_device_fingerprint() -> str:
    return secrets.token_hex(16)
