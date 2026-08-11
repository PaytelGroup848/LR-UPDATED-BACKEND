import os
import json
from copy import deepcopy
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi


ENVIRONMENT = os.getenv("ENVIRONMENT", os.getenv("LR_ENV", "development")).lower()
UPSTREAM_MAX_CONNECTIONS = int(os.getenv("UPSTREAM_MAX_CONNECTIONS", "2000"))
UPSTREAM_MAX_KEEPALIVE = int(os.getenv("UPSTREAM_MAX_KEEPALIVE", "500"))
UPSTREAM_KEEPALIVE_EXPIRY = float(os.getenv("UPSTREAM_KEEPALIVE_EXPIRY", "30"))


def _service_url(name: str, development_default: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    if ENVIRONMENT == "production":
        raise RuntimeError(f"{name} is required in production")
    return development_default


AUTH_SERVICE_URL = _service_url("AUTH_SERVICE_URL", "http://127.0.0.1:8001")
USER_SERVICE_URL = _service_url("USER_SERVICE_URL", "http://127.0.0.1:8002")
WEB_BACKEND_URL = _service_url("WEB_BACKEND_URL", "http://127.0.0.1:8004")
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]
if "*" in CORS_ORIGINS and ENVIRONMENT == "production":
    CORS_ORIGINS = [origin for origin in CORS_ORIGINS if origin != "*"]

SERVICE_ROUTES = {
    "auth": AUTH_SERVICE_URL,
}

WEB_BACKEND_ROUTES = {
    "add-server",
    "agents",
    "api",
    "apps",
    "create-file",
    "delete-file",
    "files",
    "login",
    "logout",
    "logs",
    "license",
    "paste-file",
    "portal",
    "processes",
    "read-file",
    "register",
    "roles",
    "servers",
    "services",
    "sessions",
    "static",
    "terminal",
    "test",
    "test_socket",
    "upload-file",
    "users",
    "windows",
}

OPENAPI_SERVICE_URLS = {
    "auth": AUTH_SERVICE_URL,
    "user": USER_SERVICE_URL,
}

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
}

app = FastAPI(
    title="LR Platform API Gateway",
    version="1.0.0",
)


@app.on_event("startup")
async def open_upstream_pool() -> None:
    app.state.upstream_client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=3.0),
        limits=httpx.Limits(
            max_connections=UPSTREAM_MAX_CONNECTIONS,
            max_keepalive_connections=UPSTREAM_MAX_KEEPALIVE,
            keepalive_expiry=UPSTREAM_KEEPALIVE_EXPIRY,
        ),
    )


@app.on_event("shutdown")
async def close_upstream_pool() -> None:
    await app.state.upstream_client.aclose()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _replace_refs(value: Any, ref_map: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {
            key: ref_map.get(item, item) if key == "$ref" else _replace_refs(item, ref_map)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [_replace_refs(item, ref_map) for item in value]

    return value


def _merge_service_openapi(
    base_schema: dict[str, Any],
    service_name: str,
    service_schema: dict[str, Any],
) -> None:
    base_schema.setdefault("paths", {})
    base_components = base_schema.setdefault("components", {})
    service_schema = deepcopy(service_schema)

    ref_map: dict[str, str] = {}

    for component_type, components in service_schema.get("components", {}).items():
        target_components = base_components.setdefault(component_type, {})

        for component_name, component_schema in list(components.items()):
            target_name = component_name

            if (
                target_name in target_components
                and target_components[target_name] != component_schema
            ):
                target_name = f"{service_name}_{component_name}"
                ref_map[
                    f"#/components/{component_type}/{component_name}"
                ] = f"#/components/{component_type}/{target_name}"

            target_components[target_name] = component_schema

    service_schema = _replace_refs(service_schema, ref_map)

    for path, path_schema in service_schema.get("paths", {}).items():
        if path == "/health":
            continue
        base_schema["paths"][path] = path_schema

    existing_tags = {
        tag.get("name")
        for tag in base_schema.get("tags", [])
        if isinstance(tag, dict)
    }
    for tag in service_schema.get("tags", []):
        if isinstance(tag, dict) and tag.get("name") not in existing_tags:
            base_schema.setdefault("tags", []).append(tag)
            existing_tags.add(tag.get("name"))


def custom_openapi() -> dict[str, Any]:
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description="Single public API surface for LR Platform services.",
        routes=app.routes,
    )

    warnings = []
    with httpx.Client(timeout=3.0) as client:
        for service_name, service_url in OPENAPI_SERVICE_URLS.items():
            try:
                response = client.get(f"{service_url.rstrip('/')}/openapi.json")
                response.raise_for_status()
                _merge_service_openapi(schema, service_name, response.json())
            except Exception as exc:
                warnings.append(f"{service_name}: {exc}")

    if warnings:
        schema["x-openapi-merge-warnings"] = warnings

    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "services": {
            "auth": AUTH_SERVICE_URL,
            "user": USER_SERVICE_URL,
            "web_backend": WEB_BACKEND_URL,
        },
    }


@app.api_route(
    "/{service_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy(service_path: str, request: Request) -> Response:
    service_name = service_path.split("/", 1)[0]
    authorization = request.headers.get("authorization", "")
    has_bearer_token = authorization.lower().startswith("bearer ")

    service_url = SERVICE_ROUTES.get(service_name)

    if service_name in {"users", "roles"} and has_bearer_token:
        service_url = USER_SERVICE_URL

    if service_url is None and service_name in WEB_BACKEND_ROUTES:
        service_url = WEB_BACKEND_URL

    if service_url is None:
        service_url = WEB_BACKEND_URL

    target_url = f"{service_url.rstrip('/')}/{service_path}"
    if request.url.query:
        target_url = f"{target_url}?{request.url.query}"

    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }
    if request.headers.get("host"):
        headers["x-forwarded-host"] = request.headers["host"]
    headers["x-forwarded-proto"] = request.url.scheme

    try:
        upstream_response = await request.app.state.upstream_client.request(
            method=request.method,
            url=target_url,
            content=await request.body(),
            headers=headers,
        )
    except httpx.RequestError as exc:
        payload = {
            "success": False,
            "error": "Upstream service is not reachable",
            "service_url": service_url,
            "detail": str(exc),
        }
        return Response(
            content=json.dumps(payload),
            status_code=503,
            media_type="application/json",
        )

    response_headers = {
        key: value
        for key, value in upstream_response.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
    }

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
        media_type=upstream_response.headers.get("content-type"),
    )
