import base64
import hmac
import os
import struct
import time
from hashlib import sha1
from urllib.parse import quote


def generate_secret():
    return base64.b32encode(os.urandom(20)).decode('ascii').rstrip('=')


def provisioning_uri(username, issuer, secret):
    label = quote(f'{issuer}:{username}')
    return f'otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}&digits=6&period=30'


def verify_totp(secret, token, window=1):
    token = ''.join(ch for ch in str(token or '') if ch.isdigit())
    if len(token) != 6 or not secret:
        return False

    now = int(time.time() // 30)
    return any(hmac.compare_digest(_totp(secret, now + offset), token) for offset in range(-window, window + 1))


def _totp(secret, counter):
    padded = secret + '=' * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded.upper())
    msg = struct.pack('>Q', counter)
    digest = hmac.new(key, msg, sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f'{code % 1000000:06d}'
