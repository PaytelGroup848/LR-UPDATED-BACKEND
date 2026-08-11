from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status

from backend.api.deps.database import get_db
from backend.core.config import settings
from backend.models.tenant import normalize_company_code, slugify_company
from backend.repositories.user_repository import UserRepository
from backend.schemas.auth import LoginRequest
from backend.schemas.auth import RegisterRequest
from shared.security.jwt import create_access_token
from shared.security.password import hash_password
from shared.security.password import verify_password


router = APIRouter(tags=["Auth"])


def _user_response(user):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "tenant_id": user.tenant_id,
    }


def _login_response(request: LoginRequest, db):
    company_code = normalize_company_code(request.company_code)
    if company_code:
        tenant = db["tenants"].find_one({"company_code": company_code})
        if not tenant:
            tenant = db["tenants"].find_one({
                "company_code": {"$in": [None, ""]},
                "company_slug": slugify_company(company_code),
            })
        repository = UserRepository(db, tenant.get("_id")) if tenant else None
        user = repository.get_by_username(request.username) if repository else None
    else:
        matches = list(db["users"].find({"username": request.username}).limit(2))
        if len(matches) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Company code is required for this username",
            )
        user = UserRepository(db)._wrap(matches[0]) if matches else None

    if (
        not user
        or not user.password
        or not verify_password(request.password, user.password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is disabled",
        )

    access_token = create_access_token(
        data={
            "sub": user.id,
            "username": user.username,
            "role": user.role,
            "tenant_id": user.tenant_id,
        },
        secret_key=settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
        expires_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "success": True,
        "redirect": "/portal",
        "user": {
            **_user_response(user),
        },
    }


@router.post("/auth/login")
def auth_login(request: LoginRequest, db=Depends(get_db)):
    return _login_response(request, db)


@router.post("/login")
def login_alias(request: LoginRequest, db=Depends(get_db)):
    return _login_response(request, db)


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db=Depends(get_db)):
    if not settings.LEGACY_PUBLIC_USER_REGISTRATION_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public user registration is disabled; use company registration",
        )
    username = request.username.strip() if request.username else ""
    password = request.password or ""

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required",
        )

    repository = UserRepository(db)

    if repository.exists_by_username(username):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    email = request.email or f"{username}@local.lr"
    if repository.exists_by_email(email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists",
        )

    user = repository.create(
        {
            "username": username,
            "email": email,
            "password": hash_password(password),
            "role": "USER",
            "is_active": True,
        }
    )

    return {
        "success": True,
        "message": "User registered successfully",
        **_user_response(user),
    }


@router.post("/logout")
def logout():
    return {"success": True}
