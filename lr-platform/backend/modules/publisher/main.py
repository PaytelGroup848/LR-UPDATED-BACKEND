from backend.core.app_factory import create_app
from backend.extensions import socketio


app = create_app("admin")


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=8003, debug=True)
