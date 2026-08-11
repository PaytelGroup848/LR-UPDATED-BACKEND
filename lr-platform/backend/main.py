import os
import sys
from pathlib import Path

if os.getenv("SOCKETIO_ASYNC_MODE", "").strip().lower() == "gevent":
    from gevent import monkey

    monkey.patch_all()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.app_factory import create_app
from backend.extensions import socketio

app = create_app()


def _server_port() -> int:
    return int(os.getenv("PORT", os.getenv("SERVICE_PORT", "8004")))


if __name__ == "__main__":
    port = _server_port()
    try:
        socketio.run(
            app,
            host="0.0.0.0",
            port=port,
            debug=os.getenv("FLASK_DEBUG", "true").lower() in ("1", "true", "yes", "on"),
            use_reloader=False,
            allow_unsafe_werkzeug=True,
        )
    except OSError as error:
        raise SystemExit(
            f"Could not start Flask backend on port {port}: {error}\n"
            "Port 8000 is reserved for the API gateway in this project. "
            "Run the Flask backend on 8004, or set PORT to a free port."
        ) from error
