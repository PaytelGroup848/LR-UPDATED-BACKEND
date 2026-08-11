from __future__ import annotations

from pathlib import Path

from flask import Blueprint, Response, jsonify, request, send_file
from flask_login import current_user, login_required

from backend.api.routers.auth_route import admin_required
from backend.printing.models import sanitize_document_name
from backend.printing.service import get_print_job_service


printing_bp = Blueprint("printing", __name__, url_prefix="/api/printing")


def _user_id() -> str:
    return str(current_user.id)


def _tenant_id():
    value = getattr(current_user, "tenant_id", None)
    return str(value) if value else None


def _wait_seconds() -> float:
    try:
        return min(max(float(request.args.get("wait") or 0), 0.0), 25.0)
    except (TypeError, ValueError):
        raise ValueError("wait must be a number between 0 and 25")


def _error_response(error: Exception):
    if isinstance(error, KeyError):
        return jsonify({"success": False, "error": str(error.args[0])}), 404
    if isinstance(error, PermissionError):
        return jsonify({"success": False, "error": str(error)}), 403
    if isinstance(error, (ValueError, TypeError)):
        return jsonify({"success": False, "error": str(error)}), 400
    if isinstance(error, RuntimeError):
        return jsonify({"success": False, "error": str(error)}), 409
    raise error


@printing_bp.route("/settings", methods=["GET"])
@login_required
def printing_settings():
    service = get_print_job_service()
    return jsonify({"success": True, "settings": service.settings.get(tenant_id=_tenant_id()).to_dict()}), 200


@printing_bp.route("/settings", methods=["PUT"])
@admin_required
def update_printing_settings():
    try:
        service = get_print_job_service()
        value = service.settings.update(request.get_json(silent=True) or {}, tenant_id=_tenant_id())
        if value.enabled:
            service.start()
        else:
            service.stop()
        return jsonify({"success": True, "settings": value.to_dict()}), 200
    except Exception as error:
        return _error_response(error)


@printing_bp.route("/clients/register", methods=["POST"])
@login_required
def register_print_client():
    data = request.get_json(silent=True) or {}
    try:
        registration = get_print_job_service().register_client(
            session_id=str(data.get("session_id") or ""),
            connection_id=str(data.get("connection_id") or ""),
            user_id=_user_id(),
            client_type=str(data.get("client_type") or "desktop").lower(),
            capabilities=data.get("capabilities") if isinstance(data.get("capabilities"), dict) else {},
            printers=data.get("printers") if isinstance(data.get("printers"), list) else [],
            tenant_id=_tenant_id(),
        )
        return jsonify({"success": True, "client": registration.metadata()}), 201
    except Exception as error:
        return _error_response(error)


@printing_bp.route("/clients/<connection_id>/heartbeat", methods=["POST"])
@login_required
def print_client_heartbeat(connection_id):
    data = request.get_json(silent=True) or {}
    ok = get_print_job_service().registry.heartbeat(
        str(data.get("session_id") or ""), connection_id, _user_id(), _tenant_id()
    )
    if not ok:
        return jsonify({"success": False, "error": "Print client registration was not found"}), 404
    return jsonify({"success": True}), 200


@printing_bp.route("/clients/<connection_id>", methods=["DELETE"])
@login_required
def unregister_print_client(connection_id):
    session_id = str(request.args.get("session_id") or "")
    removed = get_print_job_service().unregister_client(
        session_id, connection_id, _user_id(), _tenant_id()
    )
    return jsonify({"success": True, "removed": removed}), 200


@printing_bp.route("/clients/<connection_id>/next", methods=["GET"])
@login_required
def next_print_job(connection_id):
    session_id = str(request.args.get("session_id") or "")
    try:
        job = get_print_job_service().claim_next_job(
            session_id, connection_id, _user_id(), wait_seconds=_wait_seconds(), tenant_id=_tenant_id()
        )
        return jsonify({"success": True, "job": job.metadata() if job else None}), 200
    except Exception as error:
        return _error_response(error)


@printing_bp.route("/browser/<connection_id>/next", methods=["GET"])
@login_required
def next_browser_print_job(connection_id):
    session_id = str(request.args.get("session_id") or "")
    try:
        service = get_print_job_service()
        job = service.claim_next_job(
            session_id, connection_id, _user_id(), wait_seconds=_wait_seconds(), tenant_id=_tenant_id()
        )
        if not job:
            return jsonify({"success": True, "job": None}), 200
        if job.client_type != "browser":
            raise PermissionError("Print job is not registered to a browser client")
        token = service.issue_browser_download_token(job)
        metadata = job.metadata()
        metadata["open_url"] = f"/api/printing/jobs/{job.job_id}/download?token={token}"
        metadata["download_url"] = metadata["open_url"] + "&attachment=1"
        return jsonify({"success": True, "job": metadata}), 200
    except Exception as error:
        return _error_response(error)


@printing_bp.route("/jobs/<job_id>/chunks/<int:sequence>", methods=["GET"])
@login_required
def download_print_chunk(job_id, sequence):
    try:
        data, offset, final = get_print_job_service().get_chunk(
            job_id,
            sequence,
            session_id=str(request.args.get("session_id") or ""),
            connection_id=str(request.args.get("connection_id") or ""),
            user_id=_user_id(),
            tenant_id=_tenant_id(),
        )
        return Response(
            data,
            status=200,
            content_type="application/octet-stream",
            headers={
                "Cache-Control": "no-store, private",
                "X-Content-Type-Options": "nosniff",
                "X-Print-Chunk-Sequence": str(sequence),
                "X-Print-Chunk-Offset": str(offset),
                "X-Print-Chunk-Final": "1" if final else "0",
            },
        )
    except Exception as error:
        return _error_response(error)


@printing_bp.route("/jobs/<job_id>/result", methods=["POST"])
@login_required
def report_print_result(job_id):
    data = request.get_json(silent=True) or {}
    try:
        job = get_print_job_service().report_result(
            job_id,
            str(data.get("state") or ""),
            session_id=str(data.get("session_id") or ""),
            connection_id=str(data.get("connection_id") or ""),
            user_id=_user_id(),
            error=data.get("error"),
            tenant_id=_tenant_id(),
        )
        return jsonify({"success": True, "job": job.metadata()}), 200
    except Exception as error:
        return _error_response(error)


@printing_bp.route("/jobs/<job_id>/cancel", methods=["POST"])
@login_required
def cancel_print_job(job_id):
    try:
        job = get_print_job_service().cancel_job(job_id, user_id=_user_id(), tenant_id=_tenant_id())
        return jsonify({"success": True, "job": job.metadata()}), 200
    except Exception as error:
        return _error_response(error)


@printing_bp.route("/jobs/<job_id>/download", methods=["GET"])
@login_required
def browser_print_download(job_id):
    try:
        job = get_print_job_service().consume_browser_download(
            job_id, str(request.args.get("token") or ""), _user_id(), _tenant_id()
        )
        if not job.pdf_path.is_file():
            raise KeyError("Print document is no longer available")
        safe_name = sanitize_document_name(job.document_name).replace('"', "") + ".pdf"
        response = send_file(
            Path(job.pdf_path),
            mimetype="application/pdf",
            as_attachment=request.args.get("attachment") == "1",
            download_name=safe_name,
            conditional=False,
            max_age=0,
        )
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
    except Exception as error:
        return _error_response(error)


@printing_bp.route("/jobs", methods=["GET"])
@admin_required
def admin_print_jobs():
    jobs = get_print_job_service().list_jobs(tenant_id=_tenant_id())
    state = str(request.args.get("state") or "").strip().lower()
    if state:
        jobs = [job for job in jobs if job.get("state") == state]
    try:
        limit = min(max(int(request.args.get("limit", 200)), 1), 1000)
    except (TypeError, ValueError):
        limit = 200
    return jsonify({"success": True, "jobs": jobs[:limit]}), 200


@printing_bp.route("/status", methods=["GET"])
@admin_required
def admin_printing_status():
    service = get_print_job_service()
    jobs = service.list_jobs(tenant_id=_tenant_id())
    return jsonify({
        "success": True,
        "enabled": service.settings.get(tenant_id=_tenant_id()).enabled,
        "spool_root": str(service.capture_root / (_tenant_id() or "legacy")),
        "active_clients": service.registry.list_clients(_tenant_id()),
        "job_counts": {
            state: sum(1 for job in jobs if job.get("state") == state)
            for state in sorted({str(job.get("state")) for job in jobs})
        },
    }), 200


@printing_bp.route("/jobs/expired", methods=["DELETE"])
@admin_required
def clear_expired_print_jobs():
    count = get_print_job_service().clear_expired(_tenant_id())
    return jsonify({"success": True, "cleared": count}), 200
