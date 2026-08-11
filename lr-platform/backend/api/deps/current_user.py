from fastapi import Depends
from fastapi import HTTPException
from fastapi import status

from fastapi.security import OAuth2PasswordBearer

from backend.api.deps.database import get_db

from backend.core.config import settings

from backend.repositories.user_repository import (
    UserRepository
)

from shared.security.jwt import (
    decode_access_token
)


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db=Depends(get_db)
):

    payload = decode_access_token(
        token=token,
        secret_key=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )

    if not payload:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    user_id = payload.get("sub")

    if not user_id:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    repository = UserRepository(db)

    user = repository.get_by_id(user_id)

    if not user:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    if not user.is_active:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is disabled"
        )

    token_tenant_id = payload.get("tenant_id")
    user_tenant_id = user.tenant_id
    if token_tenant_id and str(token_tenant_id) != str(user_tenant_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token tenant does not match user tenant",
        )
    if not user_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="User tenant migration is required",
        )

    return user
