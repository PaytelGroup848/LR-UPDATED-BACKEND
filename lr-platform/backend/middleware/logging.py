import logging
import time

from flask import g, request


logger = logging.getLogger("lr-platform.requests")


def register_request_logging(app):
    @app.before_request
    def _start_timer():
        g.lr_started_at = time.perf_counter()

    @app.after_request
    def _log_response(response):
        started_at = getattr(g, "lr_started_at", None)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000) if started_at else 0
        logger.info(
            "%s %s -> %s %sms",
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
        )
        return response
