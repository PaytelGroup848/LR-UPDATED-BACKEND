import getpass
import hashlib
import platform
import socket
import uuid

import psutil


def _windows_machine_guid():
    if platform.system().lower() != "windows":
        return ""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0),
        ) as key:
            return str(winreg.QueryValueEx(key, "MachineGuid")[0]).strip()
    except OSError:
        return ""


def get_machine_id():
    seed = _windows_machine_guid()
    if not seed:
        seed = f"{platform.node()}|{uuid.getnode()}|{platform.system()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def get_ip_addresses():
    addresses = set()
    for name in {socket.gethostname(), socket.getfqdn()}:
        try:
            for item in socket.getaddrinfo(name, None, socket.AF_INET):
                address = str(item[4][0]).strip()
                if address and not address.startswith("127."):
                    addresses.add(address)
        except OSError:
            continue
    return sorted(addresses)

def get_system_info():
    machine_id = get_machine_id()
    ip_addresses = get_ip_addresses()
    return {
        "agent_id": machine_id,
        "machine_id": machine_id,
        "hostname": platform.node(),
        "fqdn": socket.getfqdn(),
        "ip_address": ip_addresses[0] if ip_addresses else "",
        "ip_addresses": ip_addresses,
        "username": getpass.getuser(),
        "os": platform.system() + " " + platform.release(),
        "cpu": platform.processor(),
        "ram": f"{round(psutil.virtual_memory().total / (1024 ** 3), 2)} GB"
    }
