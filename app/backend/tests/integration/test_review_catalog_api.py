"""Database and object lists for choosing what to review (sql-review 003 Requirement 1-2).

The SQL Server port is the signature-constrained ``FakeCatalog``; the HTTP application, roles,
validation, pages and the error mapping of 002-sql-server-connection Requirement 8 are real.
"""

from datetime import datetime

import pytest

from app.domain.sql_server import (
    CatalogObject,
    SqlServerError,
    SqlServerErrorClass,
    SqlServerNotConfigured,
)
from tests.integration.conftest import ReviewEnv

pytestmark = pytest.mark.integration


def _sql_datetime(*parts: int) -> datetime:
    # sys.objects dates are SQL Server datetime values, which carry no time zone.
    return datetime(*parts)  # noqa: DTZ001


def _object(
    schema: str, name: str, code: str, created: datetime, modified: datetime
) -> CatalogObject:
    types = {"P": "PROCEDURE", "V": "VIEW", "FN": "FUNCTION_SCALAR", "IF": "FUNCTION_INLINE"}
    return CatalogObject(schema, name, types[code], code, created, modified)


OBJECTS = [
    _object("dbo", "usp_Load", "P", _sql_datetime(2026, 1, 1), _sql_datetime(2026, 9, 1, 12)),
    _object("dbo", "vw_Musteri", "V", _sql_datetime(2026, 9, 2), _sql_datetime(2026, 9, 2)),
    _object("sales", "fn_Tutar", "FN", _sql_datetime(2025, 1, 1), _sql_datetime(2025, 6, 1)),
    _object("sales", "usp_Satis", "P", _sql_datetime(2026, 3, 1), _sql_datetime(2026, 3, 1)),
]


async def test_databases_are_listed_in_pages(review_env: ReviewEnv) -> None:
    reviewer = await review_env.sessions.reviewer()
    # 002 Requirement 7: every database the port reports is offered; system ones never are.
    review_env.catalog.databases = ["DWH", "DWH2", "master", "Stage", "tempdb"]
    client, prefix = review_env.auth.client, review_env.prefix

    first = await client.get(f"{prefix}/databases?page_size=1", headers=reviewer.headers)
    second = await client.get(f"{prefix}/databases?page=2&page_size=1", headers=reviewer.headers)
    everything = await client.get(f"{prefix}/databases", headers=reviewer.headers)

    assert first.json() == {"items": ["DWH"], "page": 1, "page_size": 1, "total": 3}
    assert second.json()["items"] == ["DWH2"]
    assert everything.json()["items"] == ["DWH", "DWH2", "Stage"]


async def test_objects_are_filtered_on_the_server_and_paged(review_env: ReviewEnv) -> None:
    manager = await review_env.sessions.rule_manager()
    review_env.catalog.objects["DWH"] = OBJECTS
    client, prefix = review_env.auth.client, review_env.prefix

    everything = (
        await client.get(f"{prefix}/databases/DWH/objects", headers=manager.headers)
    ).json()
    assert everything["total"] == 4
    assert everything["items"][0] == {
        "schema": "dbo",
        "name": "usp_Load",
        "type": "PROCEDURE",
        "type_code": "P",
        "created_at": "2026-01-01T00:00:00",
        "last_modified": "2026-09-01T12:00:00",
    }
    by_text = await client.get(f"{prefix}/databases/DWH/objects?q=USP", headers=manager.headers)
    assert [row["name"] for row in by_text.json()["items"]] == ["usp_Load", "usp_Satis"]
    by_type = await client.get(
        f"{prefix}/databases/DWH/objects?type=P&page_size=1&page=2", headers=manager.headers
    )
    assert by_type.json()["total"] == 2
    assert [row["name"] for row in by_type.json()["items"]] == ["usp_Satis"]
    by_date = await client.get(
        f"{prefix}/databases/DWH/objects?from_date=2026-09-01", headers=manager.headers
    )
    assert [row["name"] for row in by_date.json()["items"]] == ["usp_Load", "vw_Musteri"]
    assert ("list_objects", "DWH", "", "2026-09-01") in review_env.catalog.calls


@pytest.mark.parametrize(
    "query",
    ["type=U", "from_date=2026-13-01", f"q={'x' * 201}", "page=0", "page_size=501"],
)
async def test_invalid_filters_are_rejected(review_env: ReviewEnv, query: str) -> None:
    reviewer = await review_env.sessions.reviewer()
    response = await review_env.auth.client.get(
        f"{review_env.prefix}/databases/DWH/objects?{query}", headers=reviewer.headers
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_request"
    assert review_env.catalog.calls == []


@pytest.mark.parametrize("database", ["master", "TempDB", "model", "msdb"])
async def test_a_system_database_is_forbidden_without_a_call(
    review_env: ReviewEnv, database: str
) -> None:
    reviewer = await review_env.sessions.reviewer()
    response = await review_env.auth.client.get(
        f"{review_env.prefix}/databases/{database}/objects", headers=reviewer.headers
    )
    assert response.status_code == 403
    assert response.json()["detail"] == {
        "code": "database_not_allowed",
        "message": "Sistem veritabanları incelenemez.",
    }
    assert review_env.catalog.calls == []


async def test_any_other_database_is_passed_to_the_port(review_env: ReviewEnv) -> None:
    reviewer = await review_env.sessions.reviewer()
    review_env.catalog.objects["Herhangi_DB"] = OBJECTS
    response = await review_env.auth.client.get(
        f"{review_env.prefix}/databases/Herhangi_DB/objects", headers=reviewer.headers
    )
    assert response.status_code == 200 and response.json()["total"] == len(OBJECTS)


@pytest.mark.parametrize(
    ("failure", "status_code", "code"),
    [
        (SqlServerNotConfigured(), 503, "sql_connection_not_configured"),
        (SqlServerError(SqlServerErrorClass.TIMEOUT, "HYT00"), 504, "sql_timeout"),
        (SqlServerError(SqlServerErrorClass.UNREACHABLE, "08001"), 503, "sql_server_unreachable"),
        (SqlServerError(SqlServerErrorClass.LOGIN_FAILED, "28000"), 503, "sql_login_failed"),
    ],
)
async def test_sql_server_failures_map_to_fixed_classes(
    review_env: ReviewEnv, failure: Exception, status_code: int, code: str
) -> None:
    reviewer = await review_env.sessions.reviewer()
    review_env.catalog.failure = failure
    for path in ("/databases", "/databases/DWH/objects"):
        response = await review_env.auth.client.get(
            f"{review_env.prefix}{path}", headers=reviewer.headers
        )
        assert response.status_code == status_code
        assert response.json()["detail"]["code"] == code
        assert "08001" not in response.text and "HYT00" not in response.text


async def test_catalog_lists_need_a_session(review_env: ReviewEnv) -> None:
    reviewer = await review_env.sessions.reviewer()
    header = review_env.auth.settings.tenant_header
    response = await review_env.auth.client.get(
        f"{review_env.prefix}/databases", headers={header: reviewer.headers[header]}
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "not_authenticated"
    assert review_env.catalog.calls == []
