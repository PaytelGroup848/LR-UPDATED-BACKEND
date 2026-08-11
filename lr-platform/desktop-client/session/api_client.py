import json
import os
import mimetypes
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from urllib.parse import urlparse


class LRApi:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )

    def post_json(self, path, payload):
        body = json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        return self._open(request)

    def post_file(self, path, file_path):
        boundary = '----LRRemoteAccessBoundary'
        filename = os.path.basename(file_path)
        content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

        with open(file_path, 'rb') as handle:
            content = handle.read()

        body = b''.join([
            f'--{boundary}\r\n'.encode(),
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
            f'Content-Type: {content_type}\r\n\r\n'.encode(),
            content,
            f'\r\n--{boundary}--\r\n'.encode(),
        ])

        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
            method='POST',
        )
        return self._open(request)

    def get_json(self, path, timeout=20):
        request = urllib.request.Request(self.base_url + path, method='GET')
        return self._open(request, timeout=timeout)

    def get_bytes(self, url_or_path):
        url = self._url(url_or_path)
        request = urllib.request.Request(url, method='GET')
        try:
            with self.opener.open(request, timeout=20) as response:
                return response.read(), response.headers
        except urllib.error.HTTPError as error:
            try:
                data = json.loads(error.read().decode('utf-8'))
            except Exception:
                data = {'message': str(error)}
            raise RuntimeError(data.get('error') or data.get('message') or str(error))
        except Exception as error:
            raise RuntimeError(str(error))

    def get_binary(self, url_or_path):
        url = self._url(url_or_path)
        request = urllib.request.Request(url, method='GET')
        try:
            with self.opener.open(request, timeout=30) as response:
                return response.read(), response.headers
        except urllib.error.HTTPError as error:
            try:
                data = json.loads(error.read().decode('utf-8'))
            except Exception:
                data = {'message': str(error)}
            raise RuntimeError(data.get('error') or data.get('message') or str(error))
        except Exception as error:
            raise RuntimeError(str(error))

    def delete_json(self, path):
        request = urllib.request.Request(self.base_url + path, method='DELETE')
        return self._open(request)

    def _url(self, url_or_path):
        parsed = urlparse(url_or_path)
        if parsed.scheme and parsed.netloc:
            return url_or_path
        return self.base_url + url_or_path

    def _open(self, request, timeout=20):
        try:
            with self.opener.open(request, timeout=timeout) as response:
                return json.loads(response.read().decode('utf-8'))

        except urllib.error.HTTPError as error:
            try:
                data = json.loads(error.read().decode('utf-8'))
            except Exception:
                data = {'message': str(error)}

            raise RuntimeError(data.get('error') or data.get('message') or str(error))

        except Exception as error:
            raise RuntimeError(str(error))
