import hashlib
import json
import os
from urllib.parse import urljoin

from flask import request


class AppUpdateService:
    APPS = {
        "admin-panel": {
            "name": "Admin Panel",
            "file_name": "Admin Panel.exe",
            "manifest": "admin-panel.json",
            "download_path": "api/download-admin-panel",
        },
        "desktop-client": {
            "name": "Desktop Client",
            "file_name": "lr_remote_access_client.exe",
            "manifest": "desktop-client.json",
            "download_path": "api/download-client",
        },
        "lr-updater": {
            "name": "LR Updater",
            "file_name": "LR Updater.exe",
            "manifest": "lr-updater.json",
            "download_path": "api/download-updater",
        },
    }

    @staticmethod
    def _static_dir():
        return os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "static")
        )

    @staticmethod
    def _manifest_dir():
        return os.path.join(AppUpdateService._static_dir(), "app-updates")

    @staticmethod
    def get_updater_exe_path():
        return os.path.join(
            AppUpdateService._static_dir(),
            "updater",
            "LR Updater.exe",
        )

    @staticmethod
    def _manifest_path(app_id):
        app = AppUpdateService.APPS.get(app_id)
        if not app:
            return None
        return os.path.join(AppUpdateService._manifest_dir(), app["manifest"])

    @staticmethod
    def _load_manifest(app_id):
        path = AppUpdateService._manifest_path(app_id)
        if not path or not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _file_sha256(path):
        if not os.path.exists(path):
            return None
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _public_url(path):
        forwarded_host = request.headers.get("X-Forwarded-Host")
        if forwarded_host:
            scheme = request.headers.get("X-Forwarded-Proto") or request.scheme
            base_url = f"{scheme}://{forwarded_host}".rstrip("/")
        else:
            base_url = request.host_url.rstrip("/")

        return urljoin(f"{base_url}/", path.lstrip("/"))

    @staticmethod
    def get_update_info(app_id, current_version=None):
        app = AppUpdateService.APPS.get(app_id)
        if not app:
            return {
                "success": False,
                "error": "App not found",
            }, 404

        manifest = AppUpdateService._load_manifest(app_id)
        latest_version = str(manifest.get("version") or "0.0.0")
        current_version = str(current_version or "").strip()
        update_available = bool(current_version and current_version != latest_version)

        sha256 = manifest.get("sha256")
        if not sha256 and manifest.get("file_path"):
            sha256 = AppUpdateService._file_sha256(manifest["file_path"])

        return {
            "success": True,
            "app_id": app_id,
            "app_name": app["name"],
            "file_name": app["file_name"],
            "current_version": current_version,
            "latest_version": latest_version,
            "update_available": update_available,
            "download_url": AppUpdateService._public_url(app["download_path"]),
            "updater_download_url": AppUpdateService._public_url("api/download-updater"),
            "sha256": sha256,
            "released_at": manifest.get("released_at"),
        }, 200

    @staticmethod
    def get_updater_download():
        file_path = AppUpdateService.get_updater_exe_path()
        if not os.path.exists(file_path):
            return {
                "success": False,
                "error": "Updater not found",
            }

        return {
            "success": True,
            "file_path": file_path,
            "download_name": "LR Updater.exe",
        }
