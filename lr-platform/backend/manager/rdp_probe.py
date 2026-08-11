import socket


def check_tcp_reachable(host, port, timeout=4):
    host = (host or '').strip()
    try:
        port = int(port or 3389)
    except (TypeError, ValueError):
        return {
            'reachable': False,
            'error': 'RDP port must be a number',
        }
    if not host:
        return {
            'reachable': False,
            'error': 'RDP host is empty',
        }

    candidates = [host]
    if host.lower() in ('localhost', '127.0.0.1', '::1'):
        candidates.append('host.docker.internal')

    last_error = None
    for candidate in candidates:
        try:
            with socket.create_connection((candidate, port), timeout=timeout):
                return {'reachable': True, 'host': candidate, 'port': port}
        except OSError as error:
            last_error = error

    if last_error:
        return {
            'reachable': False,
            'host': host,
            'port': port,
            'error': str(last_error),
        }

    return {'reachable': False, 'host': host, 'port': port, 'error': 'Unknown connection error'}
