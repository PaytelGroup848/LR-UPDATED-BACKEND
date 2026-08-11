from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from backend.api.deps.database import (
    get_db
)

from backend.repositories.user_repository import (
    UserRepository
)

from backend.repositories.role_repository import (
    RoleRepository
)

from backend.services.user_service import (
    UserService
)

from backend.schemas.user import (
    UserCreateRequest,
    UserUpdateRequest,
)
from backend.api.deps.current_user import (
    get_current_user
)

from backend.api.deps.permissions import (
    require_role
)
from backend.models.user import User
from backend.models.server import Server


router = APIRouter(
    prefix="/users",
    tags=["Users"]
)


@router.get("/me")
def get_me(
    current_user=Depends(get_current_user)
):

    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "role_id": current_user.role_id,
        "role": current_user.role,
        "is_active": current_user.is_active
        ,"tenant_id": current_user.tenant_id
    }

@router.get("/admin-only")
def admin_only(
    current_user=Depends(
        require_role(
            "ADMIN"
        )
    )
):

    return {
        "message": (
            "Welcome Admin"
        ),
        "username": (
            current_user.username
        )
    }

@router.post("/")
def create_user(
    request: UserCreateRequest,
    db=Depends(get_db),
    current_user=Depends(
        require_role(
            "ADMIN"
        )
    )
):

    try:
        target_server = None
        if request.windows_account_enabled:
            if not request.windows_server_id:
                raise ValueError("Select the Windows server where this user account must be created")
            target_server = Server.get_by_id(
                request.windows_server_id,
                current_user.tenant_id,
            )
            if not target_server or target_server.get("is_active") is False:
                raise ValueError("Selected Windows server is not available for this company")

        service = UserService(
            UserRepository(db, current_user.tenant_id),
            RoleRepository(db)
        )

        user = service.create_user(
            username=request.username,
            email=request.email or f"{request.username}@local.lr",
            password=request.password,
            role_name=request.role_name,
            windows_username=request.windows_username,
            windows_password=request.windows_password,
            windows_domain=request.windows_domain,
            windows_account_scope=request.windows_account_scope,
            windows_account_enabled=request.windows_account_enabled,
            windows_create_account=request.windows_create_account,
            windows_server_id=target_server.get("_id") if target_server else None,
            windows_agent_id=target_server.get("agent_id") if target_server else None,
            tenant_id=current_user.tenant_id,
        )

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email
        }

    except ValueError as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    
@router.get("/")
def get_users(
    db=Depends(get_db),
    current_user=Depends(
        require_role(
            "ADMIN"
        )
    )
):

    repository = UserRepository(db, current_user.tenant_id)

    users = repository.get_all()

    return [User.to_dict(user) for user in users]

@router.get("/{user_id}")
def get_user(
    user_id: str,
    db=Depends(get_db),
    current_user=Depends(
        require_role(
            "ADMIN"
        )
    )
):

    repository = UserRepository(db, current_user.tenant_id)

    user = repository.get_by_id(
        user_id
    )

    if not user:

        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return User.to_dict(user)


@router.patch("/{user_id}")
def update_user(
    user_id: str,
    request: UserUpdateRequest,
    db=Depends(get_db),
    current_user=Depends(require_role("ADMIN")),
):
    service = UserService(UserRepository(db, current_user.tenant_id), RoleRepository(db))
    try:
        user = service.update_user(
            user_id,
            request.model_dump(exclude_unset=True),
        )
    except ValueError as error:
        status_code = 404 if str(error) == "User not found" else 400
        raise HTTPException(status_code=status_code, detail=str(error))

    return User.to_dict(user)
