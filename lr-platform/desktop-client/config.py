import os

try:
    from build_version import APP_VERSION
except ImportError:
    APP_VERSION = "0.0.0-dev"

APP_ID = "desktop-client"
APP_NAME = "Desktop Client"
# Desktop clients connect through the public API gateway. Port 8004 belongs to
# the internal web-backend service and may not be exposed to client machines.
DEFAULT_SERVER_URL = os.getenv('LR_SERVER_URL', 'http://191.44.87.38:8000')
DEFAULT_COMPANY_CODE = os.getenv('LR_COMPANY_CODE', '')
