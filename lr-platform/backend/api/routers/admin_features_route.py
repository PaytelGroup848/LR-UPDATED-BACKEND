from flask import Blueprint, jsonify, request, send_file
from flask_login import login_required, current_user

from backend.services.app_update_service import AppUpdateService
from backend.services.admin_features_service import AdminFeatureService

admin_features = Blueprint(
    "admin_features",
    __name__,
    url_prefix="/api"
)


def _data():
    return request.get_json(silent=True) or request.form.to_dict()


def _admin_required():
    return bool(
        getattr(current_user, "is_admin", False)
        or (
            hasattr(current_user, "has_role")
            and current_user.has_role("Admin")
        )
    )


def _can_manage_tickets():
    return _admin_required()


# =========================
# 2FA
# =========================

@admin_features.route("/2fa/setup", methods=["POST"])
@login_required
def setup_2fa():
    return jsonify(
        AdminFeatureService.setup_2fa(
            current_user,
            request.remote_addr
        )
    )


@admin_features.route("/2fa/enable", methods=["POST"])
@login_required
def enable_2fa():
    return jsonify(
        AdminFeatureService.enable_2fa(
            current_user,
            _data().get("token"),
            request.remote_addr
        )
    )


@admin_features.route('/2fa/disable', methods=['POST'])
@login_required
def disable_2fa():
    result = AdminFeatureService.disable_2fa(
        current_user,
        request.remote_addr
    )

    return jsonify(result)


# =========================
# TICKETS
# =========================



@admin_features.route('/tickets', methods=['GET', 'POST'])
@login_required
def tickets():

    if request.method == 'GET':
        result = AdminFeatureService.get_tickets(
            current_user,
            is_manager=_can_manage_tickets(),
            status=request.args.get('status')
        )

        return jsonify(result)

    result, status_code = AdminFeatureService.create_ticket(
        current_user,
        _data(),
        request.remote_addr
    )

    return jsonify(result), status_code


@admin_features.route(
    '/tickets/<int:ticket_id>',
    methods=['PATCH', 'POST']
)
@login_required
def update_ticket(ticket_id):

    result, status_code = (
        AdminFeatureService.update_ticket(
            ticket_id=ticket_id,
            user=current_user,
            payload=_data(),
            ip_address=request.remote_addr,
            is_manager=_can_manage_tickets()
        )
    )

    return jsonify(result), status_code


# =========================
# CLIPBOARD
# =========================

@admin_features.route(
    '/clipboard',
    methods=['GET', 'POST']
)
@login_required
def clipboard():

    if request.method == 'GET':

        result = (
            AdminFeatureService.get_clipboard_items(
                current_user,
                request.args.get('session_id')
            )
        )

        return jsonify(result)

    result, status_code = (
        AdminFeatureService.create_clipboard_item(
            current_user,
            _data(),
            request.remote_addr
        )
    )

    return jsonify(result), status_code


# =========================
# FILE TRANSFERS
# =========================

@admin_features.route(
    '/transfers',
    methods=['GET', 'POST']
)
@login_required
def transfers():

    if request.method == 'GET':

        result = (
            AdminFeatureService.get_transfers()
        )

        return jsonify(result)

    result, status_code = (
        AdminFeatureService.upload_transfer(
            current_user,
            request.files.get('file'),
            request.remote_addr
        )
    )

    return jsonify(result), status_code


@admin_features.route("/transfers", methods=["POST"])
@login_required
def upload_transfer():
    return jsonify(
        AdminFeatureService.upload_transfer(
            current_user,
            request.files,
            request.remote_addr
        )
    )


@admin_features.route(
    '/transfers/<path:name>',
    methods=['GET']
)
@login_required
def download_transfer(name):

    result, status_code = (
        AdminFeatureService.download_transfer(
            current_user,
            name,
            request.remote_addr
        )
    )

    if status_code != 200:
        return jsonify(result), status_code

    return send_file(
        result,
        as_attachment=True
    )

# =========================
# RECORDINGS
# =========================
@admin_features.route('/recordings', methods=['GET'])
@login_required
def recordings():
    result = AdminFeatureService.get_recordings(current_user)

    if isinstance(result, tuple):
        data, status = result
        return jsonify(data), status

    return jsonify(result)

@admin_features.route('/recordings/<agent_id>/start', methods=['POST'])
@login_required
def start_recording(agent_id):

    result = AdminFeatureService.start_recording(
        current_user,
        agent_id,
        request.remote_addr,
        session_id=_data().get("session_id"),
    )

    if isinstance(result, tuple):
        data, status = result
        return jsonify(data), status

    return jsonify(result)


@admin_features.route('/recordings/<agent_id>/stop', methods=['POST'])
@login_required
def stop_recording(agent_id):

    result = AdminFeatureService.stop_recording(
        current_user,
        agent_id,
        request.remote_addr,
        session_id=_data().get("session_id"),
    )

    if isinstance(result, tuple):
        data, status = result
        return jsonify(data), status

    return jsonify(result)


# =========================
# MONITORING
# =========================

@admin_features.route('/monitoring', methods=['GET'])
@login_required
def monitoring():

    result = AdminFeatureService.get_monitoring(current_user)

    if isinstance(result, tuple):
        data, status = result
        return jsonify(data), status

    return jsonify(result)


@admin_features.route('/health', methods=['GET'])
def health():

    return jsonify(
        AdminFeatureService.get_health(current_user)
    )


@admin_features.route('/user-policies/<user_id>', methods=['GET', 'POST', 'PATCH'])
@login_required
def user_policy(user_id):
    if not _admin_required():
        return jsonify({
            'success': False,
            'error': 'Forbidden'
        }), 403

    if request.method == 'GET':
        result, status_code = AdminFeatureService.get_user_policy(user_id)
        return jsonify(result), status_code

    result, status_code = AdminFeatureService.save_user_policy(
        user_id=user_id,
        payload=_data(),
        actor=current_user,
        ip_address=request.remote_addr,
    )
    return jsonify(result), status_code


@admin_features.route('/streams', methods=['GET'])
@login_required
def streams():

    result = AdminFeatureService.get_streams(
        request.args.get("agent_id"),
        current_user,
    )

    if isinstance(result, tuple):
        data, status = result
        return jsonify(data), status

    return jsonify(result)


@admin_features.route('/error-logs', methods=['GET'])
@login_required
def error_logs():

    result = AdminFeatureService.get_error_logs(
        request.args.get('limit', 100, type=int)
    )

    if isinstance(result, tuple):
        data, status = result
        return jsonify(data), status

    return jsonify(result)


# =========================
# LOGIN URLS
# =========================

@admin_features.route('/generate-portal-url', methods=['POST'])
@login_required
def generate_portal_url():
    if not _admin_required():
        return jsonify({
            'success': False,
            'error': 'Administrator permission is required',
            'code': 'admin_required',
        }), 403

    result = AdminFeatureService.generate_portal_url(
        current_user=current_user,
        ip_address=request.remote_addr,
    )
    data, status = result
    return jsonify(data), status

@admin_features.route('/generate-url', methods=['POST'])
@login_required
def generate_url():
    if not _admin_required():
        return jsonify({
            'success': False,
            'error': 'Administrator permission is required',
            'code': 'admin_required',
        }), 403

    result = AdminFeatureService.generate_url(
        payload=_data(),
        current_user=current_user,
        ip_address=request.remote_addr
    )

    data, status = result

    return jsonify(data), status




@admin_features.route('/login-links', methods=['GET'])
@login_required
def login_links():
    return jsonify(
        AdminFeatureService.get_login_links(
            current_user,
            user_id=request.args.get('user_id'),
            limit=request.args.get('limit', 100),
        )
    )


@admin_features.route(
    '/login-links/<link_id>/revoke',
    methods=['POST', 'DELETE']
)
@login_required
def revoke_login_link(link_id):

    if not _admin_required():
        return jsonify({
            'success': False,
            'error': 'Forbidden'
        }), 403

    result = AdminFeatureService.revoke_login_link(
        link_id=link_id,
        user_id=current_user.id,
        ip_address=request.remote_addr
    )

    status_code = (
        404
        if not result["success"]
        else 200
    )

    return jsonify(result), status_code


# =========================
# ALERTS
# =========================

@admin_features.route(
    '/alerts/test',
    methods=['POST']
)
@login_required
def test_alert():

    if not _admin_required():
        return jsonify({
            'success': False,
            'error': 'Forbidden'
        }), 403

    result = AdminFeatureService.test_alert(
        user_id=current_user.id,
        ip_address=request.remote_addr,
        payload=_data()
    )

    return jsonify(result)


# =========================
# AGENT
# =========================

@admin_features.route(
    '/agents/install-script',
    methods=['GET']
)
@login_required
def agent_install_script():

    if not _admin_required():
        return jsonify({
            'success': False,
            'error': 'Forbidden'
        }), 403

    result = AdminFeatureService.get_agent_install_script(
        request.args.get('server_url')
        or request.host_url.rstrip('/')
    )

    return jsonify(result)


@admin_features.route(
    '/agents/source/<path:name>',
    methods=['GET']
)
def download_agent_source(name):

    result = (
        AdminFeatureService
        .get_agent_source_path(name)
    )

    if not result["success"]:
        return jsonify(result), 404

    return send_file(
        result["file_path"],
        as_attachment=True,
        download_name=result["download_name"]
    )

# =========================
# CLIENT DOWNLOAD
# =========================

@admin_features.route(
    '/download-client',
    methods=['GET']
)
def download_client_exe():

    result = (
        AdminFeatureService
        .get_client_download()
    )

    if not result["success"]:
        return jsonify(result), 404

    return send_file(
        result["file_path"],
        as_attachment=True,
        download_name=result.get("download_name", "lr_remote_access_client.exe")
    )


@admin_features.route(
    '/download-admin-panel',
    methods=['GET']
)
def download_admin_panel_exe():

    result = (
        AdminFeatureService
        .get_admin_panel_download()
    )

    if not result["success"]:
        return jsonify(result), 404

    return send_file(
        result["file_path"],
        as_attachment=True,
        download_name=result.get("download_name", "Admin Panel.exe")
    )


@admin_features.route(
    '/download-updater',
    methods=['GET']
)
def download_updater_exe():

    result = (
        AppUpdateService
        .get_updater_download()
    )

    if not result["success"]:
        return jsonify(result), 404

    return send_file(
        result["file_path"],
        as_attachment=True,
        download_name=result.get("download_name", "LR Updater.exe")
    )


@admin_features.route(
    '/app-updates/<app_id>',
    methods=['GET']
)
def app_update_info(app_id):

    result, status_code = (
        AppUpdateService
        .get_update_info(
            app_id=app_id,
            current_version=request.args.get("current_version")
        )
    )

    return jsonify(result), status_code
