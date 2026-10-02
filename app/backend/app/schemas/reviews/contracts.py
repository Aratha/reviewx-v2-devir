"""Catalog listing, review start and review result contracts (sql-review 003 and 004).

The result shapes are shared by the live ``complete`` event and the stored run detail of
005-review-history-export; only the live event carries the reviewed SQL text.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RuleResultStatusValue = Literal["PASS", "FAIL", "NOT_APPLICABLE", "UNKNOWN"]
SeverityValue = Literal["HIGH", "MEDIUM", "LOW"]
TierValue = Literal["critical", "normal"]
ReviewKindValue = Literal["object", "script"]

# Transport bounds only; the services apply the review limits with their own error codes.
_TRANSPORT_SQL_MAX_LENGTH = 1_000_000
# Technical bound of one request body, not a product limit: a run has no object limit
# (003-object-review Decision 3). It keeps the request list finite, as rules/57 requires, far above
# a selection anyone reviews in one run; a longer list answers 422 invalid_request.
SELECTION_TECHNICAL_MAX_ITEMS = 10_000


class DatabasePage(BaseModel):
    items: list[str]
    page: int
    page_size: int
    total: int


class CatalogObjectItem(BaseModel):
    schema_: str = Field(alias="schema", serialization_alias="schema")
    name: str
    type: str
    type_code: str
    created_at: datetime | None
    last_modified: datetime | None

    model_config = {"populate_by_name": True}


class CatalogObjectPage(BaseModel):
    items: list[CatalogObjectItem]
    page: int
    page_size: int
    total: int


class ObjectSelectionItem(BaseModel):
    database: str = Field(min_length=1, max_length=128)
    schema_: str = Field(alias="schema", serialization_alias="schema", min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    type_code: str = Field(min_length=1, max_length=8)

    model_config = {"populate_by_name": True}


class ObjectReviewRequest(BaseModel):
    selections: list[ObjectSelectionItem] = Field(
        max_length=SELECTION_TECHNICAL_MAX_ITEMS,
        description="No product limit; the list length is bounded only technically.",
    )


class ScriptReviewRequest(BaseModel):
    sql: str = Field(max_length=_TRANSPORT_SQL_MAX_LENGTH)
    label: str | None = Field(default=None, max_length=_TRANSPORT_SQL_MAX_LENGTH)


class RuleResultItem(BaseModel):
    id: str = Field(description="public_id of the rule result.")
    rule_id: str
    tier: TierValue
    status: RuleResultStatusValue
    severity: SeverityValue | None = Field(description="Set only for a FAIL verdict.")
    decision_basis: str | None
    description: str
    line_reference: str
    code_snippet: str
    false_positive: bool


class FindingItem(BaseModel):
    id: str = Field(description="public_id of the finding.")
    rule_id: str
    severity: SeverityValue
    description: str
    line_reference: str
    code_snippet: str
    false_positive: bool


class ObjectResultItem(BaseModel):
    database: str = Field(description="Empty for a script run.")
    schema_: str = Field(alias="schema", serialization_alias="schema")
    name: str
    object_type: str
    type_code: str
    error_code: str | None
    error_message: str | None
    parse_warning: str | None
    rule_results: list[RuleResultItem]
    findings: list[FindingItem]

    model_config = {"populate_by_name": True}


class LiveObjectResultItem(ObjectResultItem):
    source_sql: str | None = Field(
        description="The reviewed text for display in this session; empty on an object error."
    )
