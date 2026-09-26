"""Safe test defaults loaded before application modules."""

import os

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy.engine import make_url

os.environ.setdefault("DWHCODEREVIEW_ENVIRONMENT", "test")
if not os.environ.get("DWHCODEREVIEW_JWT_PRIVATE_KEY"):
    # A per-run key keeps every test signature unrelated to any committed or deployed key.
    os.environ["DWHCODEREVIEW_JWT_PRIVATE_KEY"] = (
        ec.generate_private_key(ec.SECP256R1())
        .private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        .decode("ascii")
    )
# Unit tests never connect; integration runs receive the disposable test database URL explicitly.
os.environ.setdefault(
    "DWHCODEREVIEW_DATABASE_URL",
    "postgresql+asyncpg://localhost:5432/dwhcodereview_test",
)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("RUN_POSTGRES_INTEGRATION") == "1":
        return
    skip = pytest.mark.skip(reason="set RUN_POSTGRES_INTEGRATION=1 for PostgreSQL tests")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def postgres_database_url() -> str:
    url = os.environ["DWHCODEREVIEW_DATABASE_URL"]
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        pytest.fail("integration tests require a disposable database ending in '_test'")
    return url
