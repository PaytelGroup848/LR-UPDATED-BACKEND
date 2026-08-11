import re
import threading


def _rdp_value(text, key):
    match = re.search(
        rf"^{re.escape(key)}:s:(.*)$",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def _credential_targets(address):
    address = str(address or "").strip()
    if not address:
        return []

    targets = [f"TERMSRV/{address}"]
    host = address
    if address.startswith("[") and "]" in address:
        host = address[1:address.index("]")]
    elif address.count(":") == 1:
        candidate, port = address.rsplit(":", 1)
        if port.isdigit():
            host = candidate
    host_target = f"TERMSRV/{host}"
    if host_target not in targets:
        targets.append(host_target)
    return targets


def prepare_rdp_for_single_sign_on(content, password, credential_cache):
    """Use Windows Credential Manager without placing a password in the RDP file."""
    if not password:
        raise RuntimeError("The authenticated password is unavailable for automatic RDP sign-in")

    text = content.decode("utf-8-sig") if isinstance(content, bytes) else str(content)
    address = _rdp_value(text, "full address")
    username = _rdp_value(text, "username")
    targets = _credential_targets(address)
    if not targets or not username:
        raise RuntimeError("The RDP file is missing its server address or Windows username")

    credential_cache.store(targets, username, password)

    output = []
    replaced_prompt = False
    replaced_once = False
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        normalized = line.strip().lower()
        if normalized.startswith("prompt for credentials:i:"):
            output.append("prompt for credentials:i:0")
            replaced_prompt = True
        elif normalized.startswith("promptcredentialonce:i:"):
            output.append("promptcredentialonce:i:1")
            replaced_once = True
        elif line:
            output.append(line)
    if not replaced_prompt:
        output.append("prompt for credentials:i:0")
    if not replaced_once:
        output.append("promptcredentialonce:i:1")
    return ("\r\n".join(output) + "\r\n").encode("utf-8")


class WindowsCredentialCache:
    """Temporarily cache RDP credentials and restore prior entries on logout."""

    def __init__(self):
        self._lock = threading.Lock()
        self._backups = {}

    @staticmethod
    def _api():
        try:
            import win32cred
        except ImportError as error:
            raise RuntimeError("Windows Credential Manager support is unavailable") from error
        return win32cred

    @staticmethod
    def _backup_credential(credential):
        if not credential:
            return None
        allowed = (
            "Flags",
            "Type",
            "TargetName",
            "Comment",
            "CredentialBlob",
            "Persist",
            "Attributes",
            "TargetAlias",
            "UserName",
        )
        return {key: credential[key] for key in allowed if key in credential}

    def store(self, targets, username, password):
        import subprocess
        try:
            api = self._api()
            domain_type = getattr(api, "CRED_TYPE_DOMAIN_PASSWORD", 2)
            generic_type = getattr(api, "CRED_TYPE_GENERIC", 1)
            persist = getattr(api, "CRED_PERSIST_LOCAL_MACHINE", 2)
            with self._lock:
                for target in targets:
                    for c_type in (domain_type, generic_type):
                        key = (target, c_type)
                        if key not in self._backups:
                            try:
                                existing = api.CredRead(target, c_type, 0)
                            except Exception:
                                existing = None
                            self._backups[key] = self._backup_credential(existing)
                        try:
                            api.CredWrite({
                                "Type": c_type,
                                "TargetName": target,
                                "UserName": username,
                                "CredentialBlob": password,
                                "Persist": persist,
                                "Comment": "LR Remote Access RDP credential",
                            }, 0)
                        except Exception:
                            pass
        except Exception:
            pass

        for target in targets:
            try:
                subprocess.run(
                    ["cmdkey", f"/generic:{target}", f"/user:{username}", f"/pass:{password}"],
                    capture_output=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception:
                pass

    def restore_all(self):
        try:
            api = self._api()
        except RuntimeError:
            self._backups.clear()
            return

        with self._lock:
            backups = list(self._backups.items())
            self._backups.clear()
        for (target, credential_type), previous in backups:
            try:
                if previous:
                    api.CredWrite(previous, 0)
                else:
                    api.CredDelete(target, credential_type, 0)
            except Exception:
                pass
