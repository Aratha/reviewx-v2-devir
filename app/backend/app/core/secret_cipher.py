"""Authenticated encryption of settings the application stores in PostgreSQL.

AES-256-GCM from the ``cryptography`` package with a random 96-bit nonce per value. The context
binds a sealed value to its purpose and tenant, so it cannot be moved to another row. A stored
value is ``v1.<nonce>.<ciphertext and tag>`` in URL-safe base64. A wrong key, another context or
a changed value all fail the same way, without a library message.
"""

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES = 32
_NONCE_BYTES = 12
_TAG_BYTES = 16
_VERSION = "v1"


class SecretUnreadable(Exception):
    """The stored value cannot be opened with the configured key."""


def decode_encryption_key(value: str) -> bytes:
    """The key as standard base64 of exactly 32 bytes; the error never echoes the value."""

    try:
        key = base64.b64decode(value.strip(), validate=True)
    except binascii.Error, ValueError:
        key = b""
    if len(key) != KEY_BYTES:
        raise ValueError("the encryption key must be base64 of exactly 32 bytes")
    return key


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class SecretCipher:
    def __init__(self, key: bytes) -> None:
        if len(key) != KEY_BYTES:
            raise ValueError("the encryption key must be exactly 32 bytes")
        self._aead = AESGCM(key)

    def encrypt(self, plaintext: str, *, context: str) -> str:
        nonce = os.urandom(_NONCE_BYTES)
        sealed = self._aead.encrypt(nonce, plaintext.encode("utf-8"), context.encode("utf-8"))
        return f"{_VERSION}.{_encode(nonce)}.{_encode(sealed)}"

    def decrypt(self, stored: str, *, context: str) -> str:
        try:
            version, nonce_text, sealed_text = stored.split(".")
            nonce, sealed = _decode(nonce_text), _decode(sealed_text)
            if version != _VERSION or len(nonce) != _NONCE_BYTES or len(sealed) < _TAG_BYTES:
                raise ValueError
            return self._aead.decrypt(nonce, sealed, context.encode("utf-8")).decode("utf-8")
        except InvalidTag, ValueError, binascii.Error:
            raise SecretUnreadable() from None
