from pymongo import MongoClient
from flask_login import LoginManager
from flask_socketio import SocketIO

from backend.core.config import settings


def _split_origins(value):
    origins = [origin.strip() for origin in str(value or "").split(",") if origin.strip()]
    origins.extend([
        str(getattr(settings, "LR_SERVER_URL", "") or "").strip(),
        str(getattr(settings, "LR_BACKEND_URL", "") or "").strip(),
        str(getattr(settings, "FRONTEND_URL", "") or "").strip(),
    ])
    if settings.ENVIRONMENT != "production":
        origins.extend([
            "http://localhost:8004",
            "http://127.0.0.1:8004",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ])
    return sorted(set(origins))

client = MongoClient(
    settings.MONGODB_URL,
    serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
    connectTimeoutMS=settings.MONGODB_CONNECT_TIMEOUT_MS,
    socketTimeoutMS=settings.MONGODB_SOCKET_TIMEOUT_MS,
    waitQueueTimeoutMS=settings.MONGODB_WAIT_QUEUE_TIMEOUT_MS,
    maxPoolSize=settings.MONGODB_MAX_POOL_SIZE,
    minPoolSize=settings.MONGODB_MIN_POOL_SIZE,
    maxIdleTimeMS=settings.MONGODB_MAX_IDLE_TIME_MS,
    retryReads=True,
    retryWrites=True,
)
db = client[settings.MONGODB_DATABASE]

login_manager = LoginManager()
socketio = SocketIO(
    async_mode=settings.SOCKETIO_ASYNC_MODE or None,
    cors_allowed_origins=_split_origins(
        settings.SOCKETIO_CORS_ORIGINS or settings.CORS_ORIGINS
    ),
    message_queue=settings.SOCKETIO_MESSAGE_QUEUE or None,
    ping_interval=settings.SOCKETIO_PING_INTERVAL_SECONDS,
    ping_timeout=settings.SOCKETIO_PING_TIMEOUT_SECONDS,
    max_http_buffer_size=settings.SOCKETIO_MAX_HTTP_BUFFER_BYTES,
)
