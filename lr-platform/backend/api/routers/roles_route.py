from fastapi import APIRouter
from fastapi import Depends

from backend.api.deps.database import get_db

from backend.api.deps.permissions import (
    require_role
)

from backend.repositories.role_repository import (
    RoleRepository
)


router = APIRouter(
    prefix="/roles",
    tags=["Roles"]
)


@router.get("/")
def get_roles(
    db=Depends(get_db),
    current_user=Depends(
        require_role(
            "ADMIN"
        )
    )
):

    repository = RoleRepository(db)

    roles = repository.get_all()

    return [
        {
            "id": role.id,
            "name": role.name,
            "description": role.description
        }
        for role in roles
    ]
