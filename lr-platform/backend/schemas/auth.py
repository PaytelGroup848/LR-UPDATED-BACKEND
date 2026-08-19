from pydantic import BaseModel


class LoginRequest(BaseModel):

    username: str

    password: str

    company_code: str | None = None

    remember_me: bool = False


class RegisterRequest(BaseModel):

    username: str

    password: str

    email: str | None = None


class LoginResponse(BaseModel):

    access_token: str

    token_type: str
