from fastapi import FastAPI

from backend.api.routers.roles_route import router as roles_router
from backend.api.routers.users_route import router as users_router


app = FastAPI(
    title="LR User Service",
    version="1.0.0",
)

app.include_router(users_router)
app.include_router(roles_router)


@app.get("/health")
def health():
    return {"service": "user-service", "status": "ok"}
