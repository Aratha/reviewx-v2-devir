"""Authentication router."""

from fastapi import APIRouter

from app.api.auth.endpoints import router as endpoints_router

router = APIRouter(prefix="/auth", tags=["authentication"])
router.include_router(endpoints_router)
