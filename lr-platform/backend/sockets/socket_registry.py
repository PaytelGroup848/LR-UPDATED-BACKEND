from backend.extensions import socketio


def register_socket_handlers(spec):
    if not spec.sockets:
        return

    import backend.sockets.socket_handler
    import backend.sockets.stream_socket
    from backend.sockets.socket_handler import register_sockets

    register_sockets()


def register_rdp_namespace(spec):
    if not spec.rdp_namespace:
        return

    from backend.services.rdp_service import init_rdp_namespace

    init_rdp_namespace(socketio)
