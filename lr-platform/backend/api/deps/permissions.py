from fastapi import Depends
from fastapi import HTTPException
from fastapi import status

from backend.api.deps.current_user import (
    get_current_user
)


def _role_key(value):
    return str(value or "").replace(" ", "_").upper()


def require_role(
    *allowed_roles: str
):
    allowed = {_role_key(role) for role in allowed_roles}

    def checker(
        current_user=Depends(
            get_current_user
        )
    ):

        role_value = getattr(current_user, "role", None)
        role_name = getattr(role_value, "name", role_value)
        role_key = _role_key(role_name)

        if role_key not in allowed:

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permission denied"
            )

        return current_user

    return checker
