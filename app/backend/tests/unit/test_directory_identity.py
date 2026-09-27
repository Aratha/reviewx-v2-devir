"""UPN normalization contract (application-foundation 001 Requirement 1)."""

import pytest

from app.domain.directory import (
    InvalidDirectoryName,
    normalize_login_name,
    normalize_upn,
    validate_local_account_name,
)

pytestmark = pytest.mark.unit

SUFFIX = "corp.example.test"


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("ad.soyad", "ad.soyad@corp.example.test"),
        ("AD.Soyad", "ad.soyad@corp.example.test"),
        ("  ad.soyad  ", "ad.soyad@corp.example.test"),
        ("ad.soyad@CORP.example.test", "ad.soyad@corp.example.test"),
        # NFKC folds compatibility characters (full-width letters) before comparison.
        ("ａｄ.soyad", "ad.soyad@corp.example.test"),
    ),
)
def test_one_upn_is_produced(raw: str, expected: str) -> None:
    assert normalize_upn(raw, SUFFIX) == expected


def test_configured_suffix_is_normalized_too() -> None:
    assert normalize_upn("ad.soyad", "@Corp.Example.Test") == "ad.soyad@corp.example.test"


@pytest.mark.parametrize(
    "raw",
    (
        "",
        "   ",
        "ad.soyad@other.example.test",
        "ad.soyad@corp.example.test@corp.example.test",
        "ad soyad",
        "DOMAIN\\ad.soyad",
        "ad/soyad",
        "ad.soyad\x00",
        "@corp.example.test",
        "a" * 121,
    ),
)
def test_invalid_names_are_rejected_without_a_retry_variant(raw: str) -> None:
    with pytest.raises(InvalidDirectoryName):
        normalize_upn(raw, SUFFIX)


def test_login_name_normalization_is_the_lookup_key() -> None:
    assert normalize_login_name("  Super-Admin ") == "super-admin"


@pytest.mark.parametrize(
    "name",
    ("ad.soyad@corp.example.test", "x.CORP.EXAMPLE.TEST", "", "iki kelime", "a" * 121),
)
def test_local_account_names_cannot_look_like_directory_names(name: str) -> None:
    with pytest.raises(InvalidDirectoryName):
        validate_local_account_name(name, SUFFIX)


def test_local_account_name_is_normalized() -> None:
    assert validate_local_account_name(" Test-Reviewer ", SUFFIX) == "test-reviewer"
    # Without a configured suffix (directory disabled) only the name rules apply.
    assert validate_local_account_name("reviewer@local", "") == "reviewer@local"
