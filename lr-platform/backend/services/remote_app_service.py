import base64
import gzip
import ipaddress
import platform
import re
import socket
from datetime import datetime, timezone
from pathlib import PureWindowsPath
from typing import Any

from backend.extensions import db, socketio
from backend.core.config import settings
from backend.models.application import PublishedApp
from backend.models.server import Server
from backend.services.agent_command_service import AgentCommandService
from shared.windows.remote_app import _REMOTE_APP_SCRIPT, run_remote_app_action


def _compressed_remote_app_script():
    comp = gzip.compress(_REMOTE_APP_SCRIPT.encode("utf-8"), mtime=0)
    return "GZIP:" + base64.b64encode(comp).decode("ascii")


def _clean_text(value):
    return str(value or "").strip()


def _alias_text(value):
    value = _clean_text(value)
    if value.startswith("||"):
        value = value[2:]
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-_")
    return value.lower()


def _looks_like_executable(value):
    value = _clean_text(value)
    if not value or value.startswith("||"):
        return False
    val_lower = value.lower()
    if val_lower in {"explorer.exe", "explorer", "calc.exe", "calc", "notepad.exe", "notepad", "cmd.exe", "cmd", "powershell.exe", "powershell"}:
        return True
    if any(val_lower.endswith(ext) for ext in (".exe", ".bat", ".cmd", ".ps1", ".com", ".lnk")):
        return True
    return False


def _path_alias(value):
    value = _clean_text(value).strip('"')
    if not value:
        return ""
    return _alias_text(PureWindowsPath(value).stem)


def _is_local_host_name(value):
    val = _clean_text(value).lower()
    if not val or val in {"localhost", "127.0.0.1", "::1", "."}:
        return True
    try:
        local_names = {socket.gethostname().lower(), socket.getfqdn().lower()}
        local_names |= {v.split(".", 1)[0] for v in local_names}
    except Exception:
        local_names = set()
    if val in local_names or val.split(".", 1)[0] in local_names:
        return True
    return False


def _host_identifiers(values):
    identifiers = set()
    for raw_value in values:
        value = _clean_text(raw_value).lower()
        if not value:
            continue
        identifiers.add(value)
        try:
            ipaddress.ip_address(value.strip("[]"))
        except ValueError:
            identifiers.add(value.split(".", 1)[0])
    return identifiers


def _same_remote_app_identity(left, right):
    keys = (
        "server_id",
        "remote_app_alias",
        "rds_collection_name",
        "rds_connection_broker",
    )
    return all(_clean_text((left or {}).get(key)).lower() == _clean_text((right or {}).get(key)).lower() for key in keys)


class RemoteAppService:
    """Keeps Mongo published applications in sync with Windows RDS RemoteApps."""

    @staticmethod
    def normalize_app_fields(data, existing=None):
        incoming = dict(data or {})
        existing = existing or {}
        merged = {**existing, **incoming}

        is_folder = (
            _clean_text(merged.get("item_type")).lower() == "folder"
            or bool(_clean_text(merged.get("folder_path")))
        )

        name = _clean_text(merged.get("name"))
        program = _clean_text(merged.get("remote_app_program"))

        if is_folder:
            folder_path = (
                _clean_text(merged.get("folder_path"))
                or _clean_text(merged.get("target"))
                or _clean_text(merged.get("arguments"))
            )
            incoming["item_type"] = "folder"
            if folder_path:
                incoming["folder_path"] = folder_path
                incoming["target"] = folder_path
                if not _clean_text(incoming.get("arguments")):
                    incoming["arguments"] = folder_path
            custom_exe = (
                _clean_text(incoming.get("remote_app_file_path"))
                or _clean_text(incoming.get("initial_program"))
                or _clean_text(merged.get("remote_app_file_path"))
                or _clean_text(merged.get("initial_program"))
            )
            if custom_exe and _looks_like_executable(custom_exe) and not custom_exe.lower().endswith("explorer.exe") and custom_exe.lower() != "explorer":
                incoming["initial_program"] = custom_exe
                incoming["remote_app_file_path"] = custom_exe
                file_path = custom_exe
            else:
                incoming["initial_program"] = "explorer.exe"
                incoming["remote_app_file_path"] = "explorer.exe"
                file_path = "explorer.exe"
        else:
            file_path = _clean_text(merged.get("remote_app_file_path"))
            if not file_path and _looks_like_executable(program):
                file_path = program
            if not file_path:
                initial_program = _clean_text(merged.get("initial_program"))
                if _looks_like_executable(initial_program):
                    file_path = initial_program
            if not file_path:
                target = _clean_text(merged.get("target"))
                if _looks_like_executable(target):
                    file_path = target

        alias = ""
        if _clean_text(incoming.get("remote_app_alias")):
            alias = _alias_text(incoming.get("remote_app_alias"))
        elif "remote_app_program" in incoming and program and not _looks_like_executable(program):
            alias = _alias_text(program)
        if not alias:
            alias = _alias_text(existing.get("remote_app_alias"))
        if not alias:
            existing_program = _clean_text(existing.get("remote_app_program"))
            if existing_program and not _looks_like_executable(existing_program):
                alias = _alias_text(existing_program)
        if not alias:
            alias = _alias_text(merged.get("slug")) or _alias_text(name) or _path_alias(file_path)
        if not alias:
            alias = "application"

        incoming["remote_app_alias"] = alias
        incoming["remote_app_program"] = f"||{alias}"
        incoming["remote_app_file_path"] = file_path
        incoming["display_mode"] = "remote_app"
        incoming["launch_mode"] = "remote_app"
        return incoming

    @staticmethod
    def identity_changed(previous, current):
        return not _same_remote_app_identity(previous, current)

    @staticmethod
    def _server_for_app(app):
        server_id = (app or {}).get("server_id")
        tenant_id = (app or {}).get("tenant_id")
        server = Server.get_by_id(server_id, tenant_id)
        if not server and server_id:
            server = Server.get_by_id(server_id)
        return server

    @classmethod
    def _action_spec(cls, app, action):
        server = cls._server_for_app(app)
        alias = _alias_text(
            (app or {}).get("remote_app_alias")
            or (app or {}).get("remote_app_program")
            or (app or {}).get("slug")
            or (app or {}).get("name")
        )
        file_path = _clean_text((app or {}).get("remote_app_file_path"))
        if not file_path:
            for candidate in (
                (app or {}).get("initial_program"),
                (app or {}).get("target"),
                (app or {}).get("remote_app_program"),
            ):
                if _looks_like_executable(candidate):
                    file_path = _clean_text(candidate)
                    break

        managed_file_path = _clean_text((app or {}).get("remote_app_managed_file_path"))
        source_file_path = _clean_text((app or {}).get("remote_app_source_file_path"))
        if source_file_path and managed_file_path and file_path.lower() == managed_file_path.lower():
            file_path = source_file_path

        connection_broker = _clean_text(
            (app or {}).get("rds_connection_broker")
            or (server or {}).get("rds_connection_broker")
        )
        server_host = _clean_text((server or {}).get("host")).lower()
        if connection_broker:
            cb_lower = connection_broker.lower()
            if (
                _is_local_host_name(connection_broker)
                or (server_host and (cb_lower == server_host or cb_lower.split(".", 1)[0] == server_host.split(".", 1)[0]))
            ):
                connection_broker = ""

        payload = {
            "action": action,
            "display_name": _clean_text((app or {}).get("name")) or alias,
            "alias": alias,
            "file_path": file_path,
            "arguments": _clean_text((app or {}).get("arguments")),
            "allow_path_change": bool((app or {}).get("remote_app_published_at")),
            "collection_name": _clean_text(
                (app or {}).get("rds_collection_name")
                or (server or {}).get("rds_collection_name")
            ),
            "connection_broker": connection_broker,
            "script_override": _compressed_remote_app_script(),
        }
        return {
            "tenant_id": (app or {}).get("tenant_id"),
            "app_id": _clean_text((app or {}).get("_id") or (app or {}).get("id")),
            "server_id": _clean_text((app or {}).get("server_id")),
            "agent_id": _clean_text((server or {}).get("agent_id")),
            "action": action,
            "alias": alias,
            "collection_name": payload["collection_name"],
            "payload": payload,
            "server": server,
        }

    @staticmethod
    def _windows_agent_candidates():
        try:
            from backend.sockets.agent_socket import connected_agents
        except Exception:
            return []
        return [
            (sid, info)
            for sid, info in list(connected_agents.items())
            if "windows" in _clean_text(info.get("os")).lower()
            or _clean_text(info.get("os")).lower().startswith("win")
        ]

    @classmethod
    def _agent_sid_for_spec(cls, spec):
        tenant_id = spec.get("tenant_id")
        candidates = [
            (sid, info)
            for sid, info in cls._windows_agent_candidates()
            if tenant_id is None or str(info.get("tenant_id")) == str(tenant_id)
        ]
        requested_agent_id = _clean_text(spec.get("agent_id"))
        if requested_agent_id:
            matches = [
                sid
                for sid, info in candidates
                if _clean_text(info.get("agent_id")) == requested_agent_id
            ]
            if len(matches) == 1:
                return matches[0], None
            return None, f"Windows Agent '{requested_agent_id}' is not connected."

        server = spec.get("server") or {}
        server_values = _host_identifiers((
            server.get("host"),
            server.get("name"),
            server.get("domain"),
            server.get("hostname"),
        ))
        matched = []
        for sid, info in candidates:
            agent_values = _host_identifiers((
                info.get("hostname"),
                info.get("ip_address"),
            ))
            if agent_values & server_values:
                matched.append(sid)

        if len(matched) == 1:
            return matched[0], None
        if len(matched) > 1:
            return None, "Multiple Windows Agents match this server. Configure its Agent ID."
        if len(candidates) == 1:
            return candidates[0][0], None
        if len(candidates) > 1:
            return None, "Multiple Windows Agents are connected. Configure the selected server's Agent ID."
        return None, "The Windows Agent for the selected RDS server is offline."

    @staticmethod
    def _server_is_local(server):
        if platform.system().lower() != "windows" or not server:
            return False
        host = _clean_text(server.get("host")).lower()
        if host in {"localhost", "127.0.0.1", "::1"}:
            return True
        local_names = {socket.gethostname().lower(), socket.getfqdn().lower()}
        local_names |= {value.split(".", 1)[0] for value in local_names}
        if host in local_names or host.split(".", 1)[0] in local_names:
            return True
        try:
            local_addresses = set(socket.gethostbyname_ex(socket.gethostname())[2])
        except OSError:
            local_addresses = set()
        return host in local_addresses

    @classmethod
    def _normalize_result(cls, result):
        if not isinstance(result, dict):
            return result
        return result

    @classmethod
    def _dispatch(cls, spec, agent_sid=None):
        if not spec.get("server"):
            return {
                "success": False,
                "status": "failed",
                "message": "The selected RDP server no longer exists.",
            }
        if not spec.get("alias"):
            return {
                "success": False,
                "status": "failed",
                "message": "RemoteApp alias is required.",
            }

        # Normal fleet path: Redis-backed presence and command result routing
        # reaches the exact tenant/server Agent even when it is connected to a
        # different single-worker backend instance.
        if agent_sid is None and spec.get("server_id"):
            tenant_id = spec.get("tenant_id") or (spec.get("server") or {}).get("tenant_id")
            result = AgentCommandService.call_server(
                "sync_remote_app",
                spec.get("payload") or {},
                tenant_id=tenant_id,
                server_id=spec.get("server_id"),
                timeout=60,
            )
            if isinstance(result, dict):
                result.setdefault("transport", "agent_command")
                result = cls._normalize_result(result)
                if result.get("success"):
                    return result
            if settings.ALLOW_LEGACY_LOCAL_HOST_OPERATIONS and cls._server_is_local(spec.get("server")):
                local_result = run_remote_app_action(spec.get("payload") or {})
                if isinstance(local_result, dict):
                    local_result.setdefault("transport", "local")
                    local_result = cls._normalize_result(local_result)
                    return local_result
            return cls._normalize_result(result) if isinstance(result, dict) else {
                "success": False,
                "status": "failed",
                "message": "Windows Agent returned an invalid RemoteApp response.",
            }

        if agent_sid is None:
            matched_sid, selection_error = cls._agent_sid_for_spec(spec)
            if matched_sid:
                agent_sid = matched_sid
            elif settings.ALLOW_LEGACY_LOCAL_HOST_OPERATIONS and cls._server_is_local(spec.get("server")):
                result = run_remote_app_action(spec.get("payload") or {})
                if isinstance(result, dict):
                    result.setdefault("transport", "local")
                    return cls._normalize_result(result)
            if not agent_sid:
                return {
                    "success": False,
                    "status": "pending",
                    "message": selection_error,
                    "offline": True,
                }

        try:
            result = socketio.call(
                "sync_remote_app",
                spec.get("payload") or {},
                namespace="/agent",
                to=agent_sid,
                timeout=30,
            )
        except Exception as error:
            return {
                "success": False,
                "status": "failed",
                "message": f"Windows Agent could not sync the RemoteApp: {error}",
            }
        if not isinstance(result, dict):
            return {
                "success": False,
                "status": "failed",
                "message": "Windows Agent returned an invalid RemoteApp response.",
            }
        result.setdefault("transport", "agent")
        return cls._normalize_result(result)

    @staticmethod
    def _job_filter(spec):
        return {
            "tenant_id": spec.get("tenant_id"),
            "server_id": spec.get("server_id"),
            "app_id": spec.get("app_id"),
            "action": spec.get("action"),
        }

    @classmethod
    def _queue_job(cls, spec, result):
        now = datetime.now(timezone.utc)
        job = {
            **cls._job_filter(spec),
            "agent_id": spec.get("agent_id"),
            "payload": spec.get("payload") or {},
            "record_result": spec.get("record_result", True),
            "update_config": spec.get("update_config", True),
            "reason": _clean_text(result.get("message")),
            "updated_at": now,
        }
        db["remote_app_jobs"].update_one(
            cls._job_filter(spec),
            {"$set": job, "$setOnInsert": {"created_at": now, "attempts": 0}},
            upsert=True,
        )
        result["queued"] = True
        return result

    @classmethod
    def _clear_job(cls, spec):
        db["remote_app_jobs"].delete_one(cls._job_filter(spec))

    @staticmethod
    def discard_publish_jobs(app_id):
        db["remote_app_jobs"].delete_many({"app_id": _clean_text(app_id), "action": "publish"})

    @classmethod
    def _record_result(cls, app, action, result, update_config=True):
        if not app or not app.get("_id"):
            return
        if isinstance(result, dict):
            result = cls._normalize_result(result)
        now = datetime.now(timezone.utc)
        status = _clean_text(result.get("status")) or ("published" if result.get("success") else "failed")
        updates: dict[str, Any] = {
            "remote_app_publish_status": status,
            "remote_app_publish_message": _clean_text(result.get("message")),
            "remote_app_last_sync_at": now,
        }
        if update_config and result.get("alias"):
            updates["remote_app_alias"] = _alias_text(result.get("alias"))
            updates["remote_app_program"] = result.get("remote_app_program") or f"||{updates['remote_app_alias']}"
        if update_config and result.get("file_path"):
            updates["remote_app_file_path"] = result.get("file_path")
        if update_config and result.get("source_file_path"):
            updates["remote_app_source_file_path"] = result.get("source_file_path")
        if update_config:
            updates["remote_app_managed_file_path"] = result.get("managed_file_path") or None
            updates["remote_app_files_staged"] = bool(result.get("staged"))
        publication_mode = _clean_text(result.get("publication_mode"))
        if update_config and publication_mode:
            updates["remote_app_publication_mode"] = publication_mode
        if update_config and publication_mode == "standalone_registry":
            # Remove stale broker/collection values so later retries remain on
            # this exact standalone host instead of being routed to an old RDS
            # deployment discovered elsewhere in the domain.
            updates["rds_collection_name"] = None
            updates["rds_connection_broker"] = None
        else:
            if update_config and result.get("collection_name"):
                updates["rds_collection_name"] = result.get("collection_name")
            if update_config:
                broker_val = result.get("connection_broker")
                if broker_val and not _is_local_host_name(broker_val):
                    updates["rds_connection_broker"] = broker_val
                else:
                    updates["rds_connection_broker"] = None
        app_id_val = app.get("_id") or app.get("id")
        if app_id_val:
            try:
                from bson import ObjectId
                app_oid = ObjectId(str(app_id_val))
                id_query = {"_id": {"$in": [app_oid, str(app_id_val)]}}
            except Exception:
                id_query = {"_id": str(app_id_val)}
            PublishedApp.collection.update_one(id_query, {"$set": updates})

    @classmethod
    def _sync(cls, app, action, record_result=True, update_config=True):
        spec = cls._action_spec(app, action)
        spec["record_result"] = record_result
        spec["update_config"] = update_config
        if action == "publish":
            cls.discard_publish_jobs(spec.get("app_id"))
        result = cls._dispatch(spec)
        if isinstance(result, dict):
            result = cls._normalize_result(result)
        if result.get("success"):
            cls._clear_job(spec)
        else:
            cls._queue_job(spec, result)
        if record_result:
            cls._record_result(app, action, result, update_config=update_config)
        return result

    @classmethod
    def publish_app(cls, app):
        result = cls._sync(app, "publish")
        return cls._normalize_result(result) if isinstance(result, dict) else result

    @classmethod
    def unpublish_app(cls, app, record_result=True, update_config=True):
        cls.discard_publish_jobs((app or {}).get("_id") or (app or {}).get("id"))
        result = cls._sync(
            app,
            "remove",
            record_result=record_result,
            update_config=update_config,
        )
        return cls._normalize_result(result) if isinstance(result, dict) else result

    @classmethod
    def record_status(cls, app, action, result):
        cls._record_result(app, action, result, update_config=False)

    @classmethod
    def sync_app(cls, app):
        if not isinstance(app, dict):
            app = PublishedApp.get_by_id(app)
        if (app or {}).get("is_active") is False:
            result = cls.mark_inactive(app)
        else:
            result = cls.publish_app(app)
        return cls._normalize_result(result) if isinstance(result, dict) else result

    @classmethod
    def mark_inactive(cls, app):
        result = {
            "success": True,
            "status": "unpublished",
            "message": "Inactive application is not published to RDS.",
            "alias": _alias_text(
                (app or {}).get("remote_app_alias")
                or (app or {}).get("remote_app_program")
            ),
            "skipped": True,
        }
        cls._record_result(app, "inactive", result)
        return result

    @classmethod
    def retry_app(cls, app):
        if (app or {}).get("is_active") is False:
            status = _clean_text((app or {}).get("remote_app_publish_status")).lower()
            if status in {"pending", "failed", "published"}:
                result = cls.unpublish_app(app)
            else:
                result = cls.mark_inactive(app)
        else:
            result = cls.sync_app(app)
        return cls._normalize_result(result) if isinstance(result, dict) else result

    @classmethod
    def sync_pending_for_agent(cls, agent_sid=None):
        processed = 0
        failed = 0
        for job in db["remote_app_jobs"].find().sort("updated_at", 1):
            app = PublishedApp.get_by_id(job.get("app_id"))
            if not app:
                db["remote_app_jobs"].delete_one({"_id": job["_id"]})
                continue
            server = Server.get_by_id(job.get("server_id"))
            spec = {
                "app_id": job.get("app_id"),
                "server_id": job.get("server_id"),
                "agent_id": _clean_text((server or {}).get("agent_id")) or job.get("agent_id"),
                "action": job.get("action"),
                "alias": job.get("alias"),
                "collection_name": job.get("collection_name"),
                "record_result": job.get("record_result", True),
                "update_config": job.get("update_config", True),
                "payload": {
                    **(job.get("payload") or {}),
                    "collection_name": _clean_text(
                        (job.get("payload") or {}).get("collection_name")
                        or (server or {}).get("rds_collection_name")
                    ),
                    "connection_broker": _clean_text(
                        (job.get("payload") or {}).get("connection_broker")
                        or (server or {}).get("rds_connection_broker")
                    ),
                },
                "server": server,
            }
            target_sid, _selection_error = cls._agent_sid_for_spec(spec)
            if agent_sid and target_sid != agent_sid:
                continue
            if not target_sid:
                continue

            result = cls._dispatch(spec, agent_sid=target_sid)
            app = PublishedApp.get_by_id(job.get("app_id"))
            if result.get("success"):
                cls._clear_job(spec)
                if spec.get("record_result", True):
                    cls._record_result(
                        app,
                        spec.get("action"),
                        result,
                        update_config=spec.get("update_config", True),
                    )
                processed += 1
            else:
                db["remote_app_jobs"].update_one(
                    {"_id": job["_id"]},
                    {
                        "$set": {
                            "reason": _clean_text(result.get("message")),
                            "updated_at": datetime.now(timezone.utc),
                        },
                        "$inc": {"attempts": 1},
                    },
                )
                if spec.get("record_result", True):
                    cls._record_result(
                        app,
                        spec.get("action"),
                        result,
                        update_config=spec.get("update_config", True),
                    )
                failed += 1
        return {"success": failed == 0, "processed": processed, "failed": failed}
