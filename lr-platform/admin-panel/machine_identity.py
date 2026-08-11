import hashlib
import platform
import socket
import uuid


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


def local_machine_claim():
    seed = _windows_machine_guid()
    if not seed:
        seed = f"{platform.node()}|{uuid.getnode()}|{platform.system()}"
    machine_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    addresses = set()
    for name in {socket.gethostname(), socket.getfqdn()}:
        try:
            for item in socket.getaddrinfo(name, None, socket.AF_INET):
                address = str(item[4][0]).strip()
                if address and not address.startswith("127."):
                    addresses.add(address)
        except OSError:
            continue
    return {
        "machine_id": machine_id,
        "hostname": platform.node(),
        "fqdn": socket.getfqdn(),
        "ip_addresses": sorted(addresses),
    }
