"""Aggregate platform router mounted under the configured API prefix."""

from fastapi import APIRouter

from app.api.auth.router import router as auth_router
from app.api.health import router as health_router
from app.core.config import get_settings

# kt-scaffold:router-imports

router = APIRouter(prefix=get_settings().api_prefix)
router.include_router(health_router)
router.include_router(auth_router)
# kt-scaffold:router-registration
