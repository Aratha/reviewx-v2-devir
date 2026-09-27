"""Process liveness and schema-aware PostgreSQL readiness probes."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db.readiness import DatabaseReadiness
from app.db.session import engine

router = APIRouter(tags=["health"])

database_readiness = DatabaseReadiness(engine)


@router.get("/liveness")
async def liveness() -> dict[str, str]:
    """The process can serve requests."""

    return {"status": "alive"}


@router.get("/readiness", response_model=None)
async def readiness() -> dict[str, str] | JSONResponse:
    """Return 503 until the runtime role connects and the schema reaches the image's head."""

    if not await database_readiness.is_ready():
        return JSONResponse(status_code=503, content={"status": "not-ready"})
    return {"status": "ready"}
