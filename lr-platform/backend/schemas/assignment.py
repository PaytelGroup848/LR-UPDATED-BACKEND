from datetime import datetime

from pydantic import BaseModel


class AssignmentCreateRequest(BaseModel):
    user_id: str
    app_id: str
    is_default: bool = False


class AssignmentResponse(BaseModel):
    id: str
    user_id: str
    app_id: str
    is_enabled: bool = True
    is_default: bool = False
    assigned_at: datetime | None = None
