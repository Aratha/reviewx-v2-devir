"""The versioned directory CA bundle (application-foundation 001 Requirement 10)."""

import hashlib
from pathlib import Path

import pytest
from cryptography import x509

pytestmark = pytest.mark.unit

BUNDLE = Path(__file__).resolve().parents[2] / "certs" / "nonprod-directory-ca.crt"
# SHA-256 of the reviewed copy; a changed bundle must be reviewed and this value updated with it.
REVIEWED_SHA256 = "98ac4569bf07f7038144b967c273c7ce122db9735d74e82ddfbcc579513131d3"


def test_bundle_is_the_reviewed_public_certificate_chain() -> None:
    content = BUNDLE.read_bytes()
    assert hashlib.sha256(content).hexdigest() == REVIEWED_SHA256
    assert b"PRIVATE KEY" not in content
    certificates = x509.load_pem_x509_certificates(content)
    assert len(certificates) == 2
    for certificate in certificates:
        constraints = certificate.extensions.get_extension_for_class(x509.BasicConstraints)
        assert constraints.value.ca is True
