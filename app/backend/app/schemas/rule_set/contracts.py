"""Rule-set draft, publish and published-version contracts (sql-review 001-rule-management)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, StrictBool

RuleSetVersionSourceValue = Literal["arayuz", "ice-aktarim"]

# Transport bounds only; the service applies the rule limits (8,000 characters after trimming,
# 200 rules) with their own error codes. Blank rules are dropped before the limits apply.
_TRANSPORT_TEXT_MAX_LENGTH = 16_000
_TRANSPORT_GROUP_MAX_ITEMS = 400


class RuleItem(BaseModel):
    id: str = Field(max_length=32, description="KuralNN code.")
    text: str = Field(max_length=_TRANSPORT_TEXT_MAX_LENGTH)
    requires_metadata: StrictBool = False


class RuleSetVersionSummary(BaseModel):
    number: int
    published_at: datetime
    published_by_name: str | None = Field(
        description="Display name of the publishing rule manager; empty for the import."
    )
    source: RuleSetVersionSourceValue
    critical_count: int
    normal_count: int


class RuleSetVersionDetail(RuleSetVersionSummary):
    critical: list[RuleItem]
    normal: list[RuleItem]


class RuleSetVersionPage(BaseModel):
    items: list[RuleSetVersionSummary]
    page: int
    page_size: int
    total: int


class RuleSetWorkspace(BaseModel):
    """The draft of the tenant together with the latest published version."""

    revision: int = Field(description="Draft change counter; save and publish must send it.")
    critical: list[RuleItem]
    normal: list[RuleItem]
    latest_version: RuleSetVersionSummary | None
    draft_differs: bool = Field(description="True when the draft differs from latest_version.")
    next_rule_id: str = Field(description="First free KuralNN code for a new rule.")


class RuleSetDraftUpdate(BaseModel):
    base_revision: int = Field(ge=0)
    critical: list[RuleItem] = Field(default_factory=list, max_length=_TRANSPORT_GROUP_MAX_ITEMS)
    normal: list[RuleItem] = Field(default_factory=list, max_length=_TRANSPORT_GROUP_MAX_ITEMS)


class RuleSetPublishRequest(BaseModel):
    base_revision: int = Field(ge=0)
