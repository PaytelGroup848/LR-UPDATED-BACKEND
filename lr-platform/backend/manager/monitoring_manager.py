import shutil
import subprocess
from datetime import datetime

import psutil

from backend.models.agent import Agent


def get_server_health():
    disk = psutil.disk_usage('/')
    memory = psutil.virtual_memory()
    network = psutil.net_io_counters()
    return {
        'timestamp': datetime.utcnow().isoformat(),
        'cpu_percent': psutil.cpu_percent(interval=0.2),
        'memory_percent': memory.percent,
        'memory_used_gb': round(memory.used / (1024 ** 3), 2),
        'memory_total_gb': round(memory.total / (1024 ** 3), 2),
        'disk_percent': disk.percent,
        'disk_used_gb': round(disk.used / (1024 ** 3), 2),
        'disk_total_gb': round(disk.total / (1024 ** 3), 2),
        'network_sent_mb': round(network.bytes_sent / (1024 ** 2), 2),
        'network_recv_mb': round(network.bytes_recv / (1024 ** 2), 2),
        'boot_time': datetime.utcfromtimestamp(psutil.boot_time()).isoformat(),
    }


def get_agent_status():
    rows = list(
    Agent.collection.find().sort("last_seen", -1).limit(100))

    return {
        'total': len(rows),
        'online': sum(1 for agent in rows if agent.get("status") == 'online'),
        'offline': sum(1 for agent in rows if agent.get("status") != 'online'),
        'agents': [
            {
                'agent_id': agent.get("agent_id"),
                'hostname': agent.get("hostname"),
                'status': agent.get("status"),
                'last_seen': agent.get("last_seen").isoformat()
             if agent.get("last_seen") else None,
         }
            for agent in rows
    ],
}
def get_docker_status():
    if not shutil.which('docker'):
        return {'available': False, 'containers': [], 'message': 'docker command not found'}
    result = _run(['docker', 'ps', '--format', '{{.ID}}|{{.Names}}|{{.Status}}|{{.Image}}'])
    containers = []
    if result['success']:
        for line in result['output'].splitlines():
            parts = line.split('|')
            if len(parts) == 4:
                containers.append({'id': parts[0], 'name': parts[1], 'status': parts[2], 'image': parts[3]})
    return {'available': result['success'], 'containers': containers, 'error': result.get('error')}


def get_kubernetes_status():
    if not shutil.which('kubectl'):
        return {'available': False, 'nodes': [], 'pods': [], 'message': 'kubectl command not found'}
    nodes = _run(['kubectl', 'get', 'nodes', '-o', 'wide', '--no-headers'])
    pods = _run(['kubectl', 'get', 'pods', '-A', '-o', 'wide', '--no-headers'])
    return {
        'available': nodes['success'] or pods['success'],
        'nodes': _rows(nodes.get('output', ''), ['name', 'status', 'roles', 'age', 'version', 'internal_ip', 'external_ip', 'os_image', 'kernel', 'runtime']),
        'pods': _rows(pods.get('output', ''), ['namespace', 'name', 'ready', 'status', 'restarts', 'age', 'ip', 'node']),
        'error': nodes.get('error') or pods.get('error'),
    }


def get_full_status():
    return {
        'health': get_server_health(),
        'agents': get_agent_status(),
        'docker': get_docker_status(),
        'kubernetes': get_kubernetes_status(),
    }


def _run(args):
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=8, check=False)
        return {'success': completed.returncode == 0, 'output': completed.stdout.strip(), 'error': completed.stderr.strip()}
    except Exception as error:
        return {'success': False, 'output': '', 'error': str(error)}


def _rows(output, keys):
    items = []
    for line in output.splitlines()[:50]:
        values = line.split()
        item = {key: values[index] if index < len(values) else '' for index, key in enumerate(keys)}
        items.append(item)
    return items
