from fastapi import FastAPI

from backend.api.routers.auth_api_route import router as auth_router

app = FastAPI(
    title="LR Auth Service",
    version="1.0.0",
)

app.include_router(auth_router)


@app.get("/health")
def health():
    return {"service": "auth-service", "status": "ok"}
