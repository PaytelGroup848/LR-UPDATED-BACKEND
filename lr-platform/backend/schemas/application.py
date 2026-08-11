from pydantic import BaseModel


class ApplicationCreateRequest(BaseModel):
    name: str
    server_id: str
    slug: str | None = None
    icon: str | None = "app"
    item_type: str | None = None
    display_mode: str | None = None
    target: str | None = None
    folder_path: str | None = None
    folder_permission: str | None = None
    launch_mode: str | None = "remote_app"
    remote_app_alias: str | None = None
    remote_app_program: str | None = None
    remote_app_file_path: str | None = None
    initial_program: str | None = None
    rds_collection_name: str | None = None
    rds_connection_broker: str | None = None
    working_directory: str | None = None
    arguments: str | None = None
    description: str | None = ""
    is_active: bool = True


class ApplicationResponse(ApplicationCreateRequest):
    id: str
    server_name: str | None = None
    remote_app_publish_status: str | None = None
    remote_app_publish_message: str | None = None
