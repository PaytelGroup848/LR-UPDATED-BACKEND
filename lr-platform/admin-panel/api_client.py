import requests
import mimetypes
from pathlib import Path
from urllib.parse import urljoin


def _dict_or_empty(value):
    return value if isinstance(value, dict) else {}


class AdminApiClient:
    # Talks to the FastAPI backend on behalf of the LR Admin Panel.

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.token: str | None = None

    def _headers(self):
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    def login(self, username: str, password: str, company_code: str | None = None) -> None:
        payload = {"username": username, "password": password}
        if company_code:
            payload["company_code"] = company_code
        response = requests.post(
            f"{self.base_url}/auth/login",
            json=payload,
            timeout=10
        )
        if response.status_code >= 400:
            raise ValueError("Invalid username or password")

        self.token = response.json()["access_token"]

    # ---------------- Users / Roles ----------------

    def get_users(self):
        response = requests.get(
            f"{self.base_url}/users/",
            headers=self._headers(),
            timeout=10
        )
        response.raise_for_status()
        return response.json()

    def get_roles(self):
        response = requests.get(
            f"{self.base_url}/roles/",
            headers=self._headers(),
            timeout=10
        )
        response.raise_for_status()
        return response.json()

class ApiError(Exception):
    pass


MICROSERVICE_GATEWAY_MESSAGE = (
    "Backend URL is pointing to a legacy API gateway without "
    "the web backend proxy. Start the current gateway/web-backend stack, or "
    "set Backend URL to the Flask backend port."
)
ADMIN_REQUIRED_MESSAGE = (
    "Login successful, but this account is not an admin. "
    "Use an Admin account for the admin panel."
)


class ApiClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.user: dict | None = None

    def set_base_url(self, base_url):
        self.base_url = base_url.rstrip('/')

    def login(self, username, password, token=None, company_code=None):
        self._ensure_compatible_backend()
        payload = {'username': username, 'password': password}
        if company_code:
            payload['company_code'] = str(company_code).strip()
        if token:
            payload['token'] = token
        data = self.post('/login', payload)
        self.user = _dict_or_empty(data.get('user') if isinstance(data, dict) else None)
        role = str(self.user.get('role') or '').upper().replace(' ', '_')
        if role != 'ADMIN':
            self.user = None
            raise ApiError(ADMIN_REQUIRED_MESSAGE)
        return data

    def logout(self):
        try:
            return self.post('/logout', {})
        finally:
            self.user = None

    def health(self):
        self._ensure_compatible_backend()
        return self.get('/api/health')

    def monitoring(self):
        return self.get('/api/monitoring')

    def users(self, limit=500, offset=0, search=None):
        query = f'?limit={int(limit)}&offset={int(offset)}'
        if search:
            query += f'&q={search}'
        return self.get(f'/users{query}').get('users', [])

    def create_user(self, payload):
        return self.post('/users', payload)

    def register_company(self, payload):
        return self.post('/api/companies/register', payload)

    def create_agent_enrollment_token(self, server_id, machine):
        return self.post(
            f'/servers/{server_id}/agent-enrollment-token',
            {'machine': machine},
        )

    def revoke_agent_binding(self, server_id):
        return self.delete(f'/servers/{server_id}/agent-binding')

    def update_user(self, user_id, payload):
        return self.patch(f'/users/{user_id}', payload)

    def delete_user(self, user_id):
        return self.delete(f'/users/{user_id}')

    def user_licenses(self):
        data = self.get('/license/admin/users')
        return data if isinstance(data, dict) else {'users': [], 'summary': {}}

    def activate_user_license(self, user_id, license_key):
        return self.post(
            f'/license/admin/users/{user_id}/activate',
            {'license_key': license_key},
        )

    def servers(self):
        data = self.get('/servers')
        return data if isinstance(data, list) else data.get('servers', [])

    def apps(self):
        return self.get('/api/apps').get('apps', [])

    def create_app(self, payload):
        return self._request('POST', '/api/apps', json=payload, timeout=210)

    def update_app(self, app_id, payload):
        return self._request('PATCH', f'/api/apps/{app_id}', json=payload, timeout=210)

    def delete_app(self, app_id):
        return self._request('DELETE', f'/api/apps/{app_id}', timeout=210)

    def retry_remote_app(self, app_id):
        return self._request('POST', f'/api/apps/{app_id}/remoteapp/sync', json={}, timeout=210)

    def assignments_for_user(self, user_id):
        return self.get(f'/api/apps/assignments/user/{user_id}')

    def user_policy(self, user_id):
        return self.get(f'/api/user-policies/{user_id}')

    def save_user_policy(self, user_id, policy):
        return self.post(f'/api/user-policies/{user_id}', {'policy': policy})

    def login_links(self, user_id=None, limit=100):
        query = f'?limit={int(limit)}'
        if user_id:
            query += f'&user_id={user_id}'
        data = self.get(f'/api/login-links{query}')
        return data.get('links', []) if isinstance(data, dict) else []

    def assign_app(self, app_id, user_id, enabled=True):
        return self._request(
            'POST',
            f'/api/apps/{app_id}/assign',
            json={'user_id': user_id, 'is_enabled': enabled},
            timeout=210,
        )

    def unassign_app(self, app_id, user_id):
        return self._request(
            'DELETE',
            f'/api/apps/{app_id}/assign/{user_id}',
            timeout=210,
        )

    def generate_url(self, user_id=None, expires_minutes=60, one_time=True):
        return self.post('/api/generate-url', {
            'user_id': user_id,
            'expires_minutes': expires_minutes,
            'one_time': one_time,
        })

    def generate_portal_url(self):
        return self.post('/api/generate-portal-url', {})

    def portal_customization_draft(self):
        return self.get('/api/admin/portal-customization/draft')

    def save_portal_customization_draft(self, config):
        return self.put(
            '/api/admin/portal-customization/draft',
            {'config': config},
        )

    def publish_portal_customization(self):
        return self.post('/api/admin/portal-customization/publish', {})

    def reset_portal_customization(self):
        return self.post('/api/admin/portal-customization/reset', {})

    def upload_portal_customization_asset(self, asset_type, file_path):
        path = Path(file_path)
        content_type = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
        with path.open('rb') as handle:
            return self._request(
                'POST',
                f'/api/admin/portal-customization/upload/{asset_type}',
                files={'file': (path.name, handle, content_type)},
                timeout=30,
            )

    def portal_customization_asset(self, asset_url):
        url = urljoin(self.base_url + '/', str(asset_url).lstrip('/'))
        try:
            response = self.session.get(url, timeout=10)
        except requests.RequestException as error:
            raise ApiError(f'Unable to load preview image: {error}') from error
        if response.status_code >= 400:
            raise ApiError(f'Unable to load preview image (HTTP {response.status_code})')
        return response.content

    def sessions(self, user_id=None, status=None, limit=None):
        params = []
        if user_id:
            params.append(f'user_id={user_id}')
        if status:
            params.append(f'status={status}')
        if limit:
            params.append(f'limit={int(limit)}')
        query = '?' + '&'.join(params) if params else ''
        return self.get(f'/api/sessions/{query}').get('sessions', [])

    def session_stats(self):
        return self.get('/api/sessions/stats')

    def printing_settings(self):
        return self.get('/api/printing/settings')

    def save_printing_settings(self, payload):
        return self.put('/api/printing/settings', payload)

    def printing_status(self):
        return self.get('/api/printing/status')

    def printing_jobs(self, limit=200, state=None):
        query = f'?limit={int(limit)}'
        if state:
            query += f'&state={state}'
        return self.get(f'/api/printing/jobs{query}').get('jobs', [])

    def clear_expired_print_jobs(self):
        return self.delete('/api/printing/jobs/expired')

    def agents(self, username=None):
        query = f'?username={username}' if username else ''
        data = self.get(f'/agents{query}')
        return data if isinstance(data, list) else data.get('agents', [])

    def streams(self):
        data = self.get('/api/streams')
        streams = data.get('streams', []) if isinstance(data, dict) else data
        if isinstance(streams, dict):
            streams = streams.get('items', [])
        return streams if isinstance(streams, list) else []

    def error_logs(self, limit=100):
        data = self.get(f'/api/error-logs?limit={int(limit)}')
        errors = data.get('errors', []) if isinstance(data, dict) else data
        return errors if isinstance(errors, list) else []

    def logs(self, limit=100, user_id=None):
        query = f'?limit={int(limit)}'
        if user_id:
            query += f'&user_id={user_id}'
        data = self.get(f'/logs{query}')
        logs = data.get('logs', []) if isinstance(data, dict) else data
        return logs if isinstance(logs, list) else []

    def get(self, path):
        return self._request('GET', path)

    def post(self, path, payload=None):
        return self._request('POST', path, json=payload or {})

    def put(self, path, payload=None):
        return self._request('PUT', path, json=payload or {})

    def patch(self, path, payload=None):
        return self._request('PATCH', path, json=payload or {})

    def delete(self, path):
        return self._request('DELETE', path)

    def _request(self, method, path, **kwargs):
        url = urljoin(self.base_url + '/', path.lstrip('/'))
        timeout = kwargs.pop('timeout', 10)
        try:
            response = self.session.request(method, url, timeout=timeout, **kwargs)
        except requests.RequestException as error:
            message = str(error)
            if 'user-service' in message or 'auth-service' in message:
                raise ApiError(MICROSERVICE_GATEWAY_MESSAGE) from error
            raise ApiError(f'Connection failed: {error}') from error

        content_type = response.headers.get('content-type', '')
        is_json = 'application/json' in content_type
        if is_json:
            data = response.json()
        else:
            data = {'message': response.text.strip()}

        if response.status_code >= 400:
            if not is_json:
                message = (
                    'This feature is not available on the running backend. '
                    'Update or restart the LR web backend.'
                    if response.status_code == 404
                    else f'Backend request failed (HTTP {response.status_code}).'
                )
            else:
                message = data.get('error') or data.get('message') or f'HTTP {response.status_code}'
            if message == 'Service route not found':
                raise ApiError(MICROSERVICE_GATEWAY_MESSAGE)
            raise ApiError(message)
        return data

    def _ensure_compatible_backend(self):
        health_url = urljoin(self.base_url + '/', 'health')
        try:
            response = self.session.get(health_url, timeout=5)
        except requests.RequestException:
            return

        content_type = response.headers.get('content-type', '')
        if 'application/json' not in content_type:
            return

        try:
            data = response.json()
        except ValueError:
            return

        services = data.get('services')
        if (
            isinstance(services, dict)
            and {'auth', 'user', 'license'}.issubset(services)
            and 'web_backend' not in services
        ):
            raise ApiError(MICROSERVICE_GATEWAY_MESSAGE)
