"""Process liveness and PostgreSQL readiness probes."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine

router = APIRouter(tags=["health"])


async def database_is_ready() -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False


@router.get("/liveness")
async def liveness() -> dict[str, str]:
    """The process can serve requests."""

    return {"status": "alive"}


@router.get("/readiness", response_model=None)
async def readiness() -> dict[str, str] | JSONResponse:
    """Return 503 until PostgreSQL accepts a trivial query."""

    if not await database_is_ready():
        return JSONResponse(status_code=503, content={"status": "not-ready"})
    return {"status": "ready"}
