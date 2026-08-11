import requests


class ApiClient:
    def __init__(self, base_url, timeout=15):
        self.base_url = str(base_url or "").rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def _url(self, path):
        return f"{self.base_url}/{str(path).lstrip('/')}"

    def get(self, path, **params):
        response = self.session.get(self._url(path), params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def post(self, path, data=None, json=None, files=None):
        response = self.session.post(
            self._url(path),
            data=data,
            json=json,
            files=files,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()
