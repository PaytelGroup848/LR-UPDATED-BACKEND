import logging
import os
from logging.handlers import RotatingFileHandler

from flask import has_app_context

from backend.models.activity_log import ActivityLog


def configure_logging(app):
    log_dir = os.path.join(app.instance_path, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'app.log')
    if any(isinstance(handler, RotatingFileHandler) and handler.baseFilename == log_file for handler in app.logger.handlers):
        return log_file

    handler = RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=5)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    logging.getLogger('werkzeug').addHandler(handler)
    return log_file


def get_logger(name='lr_remote_access'):
    return logging.getLogger(name)


def recent_error_lines(app, limit=100):
    log_file = os.path.join(app.instance_path, 'logs', 'app.log')
    if not os.path.isfile(log_file):
        return []
    with open(log_file, 'r', encoding='utf-8', errors='replace') as handle:
        lines = [line.rstrip() for line in handle.readlines() if ' ERROR ' in line or ' CRITICAL ' in line]
    return lines[-limit:]


def add_log(user_id, action):
    ActivityLog.log(user_id=user_id, action=action, category='system')
    if has_app_context():
        logging.getLogger('lr_remote_access.audit').info('user_id=%s action=%s', user_id, action)
