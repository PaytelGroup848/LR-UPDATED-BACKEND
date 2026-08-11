from datetime import datetime
from datetime import timedelta

from jose import JWTError
from jose import jwt


def create_access_token(
    data: dict,
    secret_key: str,
    algorithm: str,
    expires_minutes: int
):
    payload = data.copy()

    expire = datetime.utcnow() + timedelta(
        minutes=expires_minutes
    )

    payload["exp"] = expire

    return jwt.encode(
        payload,
        secret_key,
        algorithm=algorithm
    )


def decode_access_token(
    token: str,
    secret_key: str,
    algorithm: str
):

    try:

        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[algorithm]
        )

        return payload

    except JWTError:

        return None