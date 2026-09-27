"""Complete SQLAlchemy model registry imported by Alembic and operational scripts."""

from app.db.base_class import Base  # noqa: F401

# Alembic imports this module to populate Base.metadata. Keep the imports here.
from app.domain.models.llm_call import LlmCallSummary  # noqa: F401
from app.domain.models.permission import Permission, RolePermission  # noqa: F401
from app.domain.models.refresh_session import RefreshSession  # noqa: F401
from app.domain.models.review import (  # noqa: F401
    ReviewFinding,
    ReviewRuleResult,
    ReviewRun,
    ReviewRunObject,
)
from app.domain.models.role import Role, UserRole  # noqa: F401
from app.domain.models.rule_set import (  # noqa: F401
    RuleSetDraft,
    RuleSetDraftRule,
    RuleSetVersion,
    RuleSetVersionRule,
)
from app.domain.models.tenant import Tenant  # noqa: F401
from app.domain.models.user import User  # noqa: F401
from app.domain.models.user_change import UserChange  # noqa: F401

# kt-scaffold:model-registry
