from datetime import datetime

from pydantic import BaseModel


class SessionLaunchRequest(BaseModel):
    server_id: str | None = None
    app_id: str | None = None
    application_id: str | None = None


class SessionResponse(BaseModel):
    id: str
    user_id: str | None = None
    server_id: str | None = None
    published_app_id: str | None = None
    connection_type: str | None = None
    display_mode: str | None = None
    launch_mode: str | None = None
    status: str | None = None
    started_at: datetime | str | None = None
    last_seen_at: datetime | str | None = None
    ended_at: datetime | str | None = None
    duration_seconds: int | None = None
