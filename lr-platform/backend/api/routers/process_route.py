from flask import Blueprint, request
from flask_login import current_user, login_required

from backend.services.process_service import ProcessService
from backend.tenancy.privileged import require_configured_agent

process = Blueprint("process", __name__)
process.before_request(require_configured_agent)


@process.route("/processes", methods=["GET"])
@login_required
def processes():

    response, status_code = ProcessService.list_processes()

    return response, status_code


@process.route("/kill-process", methods=["POST"])
@login_required
def kill():

    response, status_code = ProcessService.kill_process(
        request.form.get("pid"),
        current_user.id
    )

    return response, status_code
