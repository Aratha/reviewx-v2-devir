"""Authenticated encryption of stored settings (sql-review/PRDs/002-sql-server-connection).

Requirement 10 and Decision 13 (Acceptance 1): the stored value never contains the plain text, a
changed key, a changed value or another context cannot be read, and a key must be 32 bytes.
"""

import base64
import os
from uuid import uuid4

import pytest

from app.core.secret_cipher import SecretCipher, SecretUnreadable, decode_encryption_key

pytestmark = pytest.mark.unit

CONTEXT = "sql-connection-password:tenant-a"


def _key() -> bytes:
    return os.urandom(32)


def test_a_sealed_value_opens_only_with_the_same_key_and_context() -> None:
    secret = f"parola-{uuid4().hex};=}}{{ ğüş"
    cipher = SecretCipher(_key())

    sealed = cipher.encrypt(secret, context=CONTEXT)

    assert cipher.decrypt(sealed, context=CONTEXT) == secret
    assert secret not in sealed and secret.encode() not in base64.urlsafe_b64decode(
        sealed.split(".")[2] + "=="
    )
    with pytest.raises(SecretUnreadable):
        SecretCipher(_key()).decrypt(sealed, context=CONTEXT)
    with pytest.raises(SecretUnreadable):
        cipher.decrypt(sealed, context="sql-connection-password:tenant-b")


def test_the_same_value_is_sealed_differently_every_time() -> None:
    cipher = SecretCipher(_key())
    assert cipher.encrypt("x", context=CONTEXT) != cipher.encrypt("x", context=CONTEXT)


@pytest.mark.parametrize("change", ["flip", "truncate", "version", "parts", "not-base64", "empty"])
def test_a_changed_or_malformed_value_is_unreadable(change: str) -> None:
    cipher = SecretCipher(_key())
    version, nonce, body = cipher.encrypt("parola", context=CONTEXT).split(".")
    flipped = ("A" if body[0] != "A" else "B") + body[1:]
    damaged = {
        "flip": f"{version}.{nonce}.{flipped}",
        "truncate": f"{version}.{nonce}.{body[:8]}",
        "version": f"v0.{nonce}.{body}",
        "parts": f"{version}.{nonce}",
        "not-base64": f"{version}.{nonce}.***",
        "empty": "",
    }[change]
    with pytest.raises(SecretUnreadable) as raised:
        cipher.decrypt(damaged, context=CONTEXT)
    # The error never carries the stored value or a library message.
    assert str(raised.value) == "" and raised.value.__cause__ is None


def test_the_key_is_base64_of_exactly_32_bytes() -> None:
    raw = _key()
    assert decode_encryption_key(base64.b64encode(raw).decode()) == raw
    assert decode_encryption_key(f"  {base64.b64encode(raw).decode()}\n") == raw
    for invalid in (
        "",
        "kisa",
        base64.b64encode(os.urandom(16)).decode(),
        base64.b64encode(os.urandom(33)).decode(),
        "not base64 at all !!",
    ):
        with pytest.raises(ValueError, match="32 bytes") as raised:
            decode_encryption_key(invalid)
        assert invalid == "" or invalid not in str(raised.value)
