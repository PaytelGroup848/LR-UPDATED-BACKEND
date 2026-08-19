import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data):
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _protect(data):
    if not hasattr(ctypes, "windll"):
        raise RuntimeError("Agent credential protection requires Windows DPAPI")
    source, source_buffer = _blob(data)
    output = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), "LR Client", None, None, None, 0, ctypes.byref(output)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def _unprotect(data):
    if not hasattr(ctypes, "windll"):
        raise RuntimeError("Agent credential protection requires Windows DPAPI")
    source, source_buffer = _blob(data)
    output = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


class AgentCredentialStore:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        try:
            encoded = self.path.read_text(encoding="ascii")
            data = json.loads(_unprotect(base64.b64decode(encoded)).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            self.clear()
            return {}

    def save(self, payload):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        protected = _protect(json.dumps(payload).encode("utf-8"))
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(base64.b64encode(protected).decode("ascii"), encoding="ascii")
        temporary.replace(self.path)

    def clear(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


def get_client_credential_store(path: Path | None = None) -> AgentCredentialStore:
    if path is not None:
        return AgentCredentialStore(path)
    local_appdata = Path(os.getenv("LOCALAPPDATA") or Path.home())
    store_path = local_appdata / "LR Remote Access" / "client_credentials.dpapi"
    return AgentCredentialStore(store_path)
