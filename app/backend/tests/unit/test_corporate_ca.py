"""The organization root CA added to the backend image trust store.

sql-review/PRDs/006-llm-connection Requirement 5 (and 002-sql-server-connection Decision 6).
"""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography import x509

pytestmark = pytest.mark.unit

CERTIFICATE = Path(__file__).resolve().parents[2] / "certs" / "corporate-inference-root.crt"
# SHA-256 of the reviewed public certificate copied from the previous application.
REVIEWED_SHA256 = "b71be69ffcb25e13684497aa3a5788c17d688a08e44f9bdc99ad1cc480677fc2"


def test_the_trust_store_addition_is_the_reviewed_public_root_certificate() -> None:
    content = CERTIFICATE.read_bytes()
    assert hashlib.sha256(content).hexdigest() == REVIEWED_SHA256
    assert b"PRIVATE KEY" not in content
    (certificate,) = x509.load_pem_x509_certificates(content)
    assert certificate.issuer == certificate.subject
    assert certificate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert certificate.not_valid_after_utc > datetime(2037, 1, 1, tzinfo=UTC)
