from pydantic import BaseModel
from pydantic import EmailStr


class UserCreateRequest(BaseModel):

    username: str

    email: EmailStr | None = None

    password: str

    role_name: str = "User"

    windows_username: str | None = None

    windows_password: str | None = None

    windows_domain: str | None = None

    windows_account_scope: str | None = None

    windows_account_enabled: bool = True

    windows_create_account: bool = True

    windows_server_id: str | None = None

    windows_agent_id: str | None = None


class UserUpdateRequest(BaseModel):

    email: EmailStr | None = None

    password: str | None = None

    role_name: str | None = None

    is_active: bool | None = None

    windows_username: str | None = None

    windows_password: str | None = None

    windows_domain: str | None = None

    windows_account_scope: str | None = None

    windows_account_enabled: bool | None = None


class UserResponse(BaseModel):

    id: str

    username: str

    email: EmailStr

    role_id: int | None = None

    role: str | None = None

    is_active: bool

    model_config = {
        "from_attributes": True
    }
