"""Password and JWT contract tests."""

import hashlib
import hmac
import json
import secrets
import string
from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jwt import InvalidTokenError
from pydantic import ValidationError

from app.core.config import MigrationSettings, Settings, get_settings
from app.core.security import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

pytestmark = pytest.mark.unit


def _pem(key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")


def _publicly_factored_rsa_key() -> rsa.RSAPrivateKey:
    """An RSA key below 2048 bits whose factors are the public Mersenne primes 2^607-1 and 2^521-1.

    It holds no secret and protects nothing. It proves that the settings reject undersized RSA
    keys without generating a weak key at run time or storing key material in the repository.
    """
    p, q, e = 2**607 - 1, 2**521 - 1, 65537
    d = pow(e, -1, (p - 1) * (q - 1))
    return rsa.RSAPrivateNumbers(
        p=p,
        q=q,
        d=d,
        dmp1=rsa.rsa_crt_dmp1(d, p),
        dmq1=rsa.rsa_crt_dmq1(d, q),
        iqmp=rsa.rsa_crt_iqmp(p, q),
        public_numbers=rsa.RSAPublicNumbers(e, p * q),
    ).private_key()


def _segment(value: dict[str, object]) -> str:
    raw = json.dumps(value, separators=(",", ":")).encode()
    return urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _valid_claims() -> dict[str, object]:
    settings = get_settings()
    now = datetime.now(UTC)
    return {
        "sub": str(uuid4()),
        "username": "admin",
        "tenant_id": str(uuid4()),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }


def test_missing_jwt_private_key_fails_configuration_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DWHCODEREVIEW_JWT_PRIVATE_KEY", raising=False)

    with pytest.raises(ValidationError, match="jwt_private_key"):
        Settings(_env_file=None)


@pytest.mark.parametrize("algorithm", ("HS256", "HS384", "HS512", "none", "ES384"))
def test_algorithms_outside_the_profile_fail_configuration_closed(algorithm: str) -> None:
    with pytest.raises(ValidationError, match="jwt_algorithm"):
        Settings(_env_file=None, jwt_algorithm=algorithm)


def test_default_profile_is_es256() -> None:
    assert Settings(_env_file=None).jwt_algorithm == "ES256"


@pytest.mark.parametrize(
    ("algorithm", "key"),
    (
        ("ES256", rsa.generate_private_key(public_exponent=65537, key_size=2048)),
        ("ES256", ec.generate_private_key(ec.SECP384R1())),
        ("RS256", ec.generate_private_key(ec.SECP256R1())),
    ),
)
def test_key_must_match_the_algorithm(
    algorithm: str, key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey
) -> None:
    with pytest.raises(ValidationError, match=algorithm):
        Settings(_env_file=None, jwt_algorithm=algorithm, jwt_private_key=_pem(key))


def test_rs256_rejects_an_rsa_key_below_the_minimum_size() -> None:
    key = _publicly_factored_rsa_key()
    assert key.key_size < 2048

    with pytest.raises(ValidationError, match="RS256 requires an RSA private key of at least 2048"):
        Settings(_env_file=None, jwt_algorithm="RS256", jwt_private_key=_pem(key))


def test_rs256_profile_signs_with_an_rsa_key() -> None:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = Settings(_env_file=None, jwt_algorithm="RS256", jwt_private_key=_pem(key))
    token = jwt.encode(_valid_claims(), settings.jwt_signing_key, algorithm="RS256")

    claims = jwt.decode(
        token,
        settings.jwt_verification_key,
        algorithms=[settings.jwt_algorithm],
        audience=settings.jwt_audience,
    )

    assert claims["username"] == "admin"


def test_invalid_key_is_rejected_without_echoing_key_material() -> None:
    material = "not-a-pem-key-sentinel-value"
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, jwt_private_key=material)

    assert "unencrypted PEM private key" in str(error.value)
    assert material not in str(error.value)


def test_symmetric_token_is_rejected() -> None:
    header = _segment({"alg": "HS256", "typ": "JWT"})
    payload = _segment(_valid_claims())
    public_pem = get_settings().jwt_verification_key.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    # Algorithm confusion: an HMAC signature keyed with the public verification key.
    signature = hmac.new(public_pem, f"{header}.{payload}".encode(), hashlib.sha256).digest()
    token = f"{header}.{payload}.{urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')}"

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_unsigned_token_is_rejected() -> None:
    token = f"{_segment({'alg': 'none', 'typ': 'JWT'})}.{_segment(_valid_claims())}."

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_token_signed_by_another_key_is_rejected() -> None:
    foreign = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(_valid_claims(), foreign, algorithm="ES256")

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


@pytest.mark.parametrize(
    ("name", "value"),
    (
        ("LANGSMITH_API_KEY", "lsv2-placeholder"),
        ("LANGCHAIN_API_KEY", "lsv2-placeholder"),
        ("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"),
        ("LANGGRAPH_API_KEY", "lsv2-placeholder"),
        ("LANGSMITH_TRACING", "true"),
        ("LANGCHAIN_TRACING_V2", "1"),
    ),
)
def test_hosted_llm_services_fail_configuration_closed(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError, match=name):
        Settings(_env_file=None)


def test_disabled_llm_tracing_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    assert Settings(_env_file=None).jwt_algorithm == "ES256"


def test_migration_settings_require_only_the_database_boundary() -> None:
    settings = MigrationSettings(
        database_url="postgresql+asyncpg://app:password@postgres:5432/app_test",
        _env_file=None,
    )

    assert settings.database_url.endswith("/app_test")


def _password(length: int) -> str:
    """Return a throwaway lowercase-only test-process credential of ``length`` characters."""

    return "".join(secrets.choice(string.ascii_lowercase) for _ in range(length))


def test_password_hash_round_trip() -> None:
    password = _password(24)
    encoded = hash_password(password)
    assert password not in encoded
    assert verify_password(password, encoded)
    assert not verify_password(password + "x", encoded)


def test_unknown_account_fails_verification() -> None:
    assert not verify_password(_password(24), None)


def test_password_below_the_password_only_minimum_is_rejected() -> None:
    assert PASSWORD_MIN_LENGTH == 15
    with pytest.raises(ValueError, match="at least 15"):
        hash_password(_password(14))


@pytest.mark.parametrize("length", (PASSWORD_MIN_LENGTH, 64, PASSWORD_MAX_LENGTH))
def test_single_character_class_password_is_accepted(length: int) -> None:
    password = _password(length)
    assert verify_password(password, hash_password(password))


def test_password_above_the_bound_is_rejected() -> None:
    assert PASSWORD_MAX_LENGTH >= 64
    with pytest.raises(ValueError, match="at most"):
        hash_password(_password(PASSWORD_MAX_LENGTH + 1))


@pytest.mark.parametrize(
    "password",
    ("PasswordPassword", "a" * 20, "abc" * 6, "1234" * 5),
    ids=("common", "one-character", "short-unit", "digit-unit"),
)
def test_common_and_repetitive_passwords_are_rejected(password: str) -> None:
    with pytest.raises(ValueError, match="too common"):
        hash_password(password)


def test_password_containing_the_account_name_is_rejected() -> None:
    username = _password(6)
    with pytest.raises(ValueError, match="account name"):
        hash_password(f"{_password(10)}{username.upper()}", context=(username,))


def test_password_spaces_and_unicode_are_kept() -> None:
    password = f" {_password(8)} şğüöçı {_password(8)} "
    encoded = hash_password(password)

    assert verify_password(password, encoded)
    assert not verify_password(password.strip(), encoded)
    assert not verify_password(password.replace("ş", "s"), encoded)


def test_access_token_round_trip() -> None:
    user_id = uuid4()
    tenant_id = uuid4()
    token = create_access_token(
        subject=user_id,
        username="admin",
        tenant_id=tenant_id,
        roles=["super_admin"],
        permissions=["platform:access"],
        is_super_admin=True,
    )
    claims = decode_access_token(token)
    assert claims.sub == user_id
    assert claims.tenant_id == tenant_id
    assert claims.is_super_admin is True


def test_tampered_token_is_rejected() -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token("not.a.valid-token")
