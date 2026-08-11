import shlex
import subprocess

from flask_socketio import emit
from backend.extensions import socketio
from backend.manager.logger import get_logger

logger = get_logger(__name__)

def register_sockets():
    from backend.sockets import agent_socket
    from backend.sockets import stream_socket
    agent_socket.register_socket_events(socketio)
    stream_socket.register_socket_events(socketio)

def register_socket_events(socketio):

    @socketio.on('connect')
    def connect():
        logger.info("Client connected")

        emit(
            'message',
            {'data': 'Connected'}
        )
    @socketio.on('terminal_command')
    def handle_terminal_command(data):

        command = data.get('command')
        try:
            args = shlex.split(command or '')
            if not args:
                raise ValueError('Command is required')
            result = subprocess.run(args, shell=False, capture_output=True, text=True, timeout=30, check=False)
            output, error = result.stdout, result.stderr
        except Exception as exc:
            output, error = '', str(exc)
        emit(
            'terminal_output',
            {'output': output, 'error': error}
        )
