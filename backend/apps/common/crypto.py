"""Symmetric encryption for user AWS credentials.

Credentials are encrypted as soon as they reach the API and only ever travel
through Redis / Postgres / Celery as ciphertext. They are decrypted in-memory
inside the Celery worker right before an S3/Spark call, and never logged,
serialized back to the client, or written to disk in plaintext.
"""
import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    key = settings.CREDENTIALS_ENCRYPTION_KEY
    if key:
        return Fernet(key.encode() if isinstance(key, str) else key)
    # Dev fallback: derive a stable 32-byte key from SECRET_KEY.
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_credentials(data: dict) -> str:
    """Encrypt a dict of sensitive credentials into an opaque token string."""
    payload = json.dumps(data, separators=(",", ":")).encode()
    return _fernet().encrypt(payload).decode()


def decrypt_credentials(token: str) -> dict:
    """Reverse of :func:`encrypt_credentials`. Raises ValueError if tampered."""
    try:
        payload = _fernet().decrypt(token.encode())
    except (InvalidToken, ValueError) as exc:
        raise ValueError("Could not decrypt credentials token") from exc
    return json.loads(payload.decode())
