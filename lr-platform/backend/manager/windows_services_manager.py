import subprocess

def get_services():
    result = subprocess.run(['sc', 'query', 'state=all'], capture_output=True, text=True)
    return result.stdout

def start_service(service_name):
    result = subprocess.run(['sc', 'start', service_name], capture_output=True, text=True)
    return result.stdout or result.stderr

def stop_service(service_name):
    result = subprocess.run(['sc', 'stop', service_name], capture_output=True, text=True)
    return result.stdout or result.stderr