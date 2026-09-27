"""Review history, false-positive and deletion contracts (sql-review 005-review-history-export)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, StrictBool

from app.schemas.reviews.contracts import ObjectResultItem, ReviewKindValue

ReviewRunStatusValue = Literal["running", "completed", "failed", "cancelled", "interrupted"]
ReviewRunScopeValue = Literal["mine", "all"]


class ReviewRunSummary(BaseModel):
    id: str = Field(description="public_id of the run.")
    kind: ReviewKindValue
    status: ReviewRunStatusValue
    started_at: datetime
    finished_at: datetime | None
    title: str
    subtitle: str | None
    error_code: str | None
    error_message: str | None
    rule_version: int
    object_count: int
    finding_count: int
    owner_display_name: str
    owned: bool = Field(description="True when the caller started the run.")


class ReviewRunPage(BaseModel):
    items: list[ReviewRunSummary]
    page: int
    page_size: int
    total: int


class ReviewRunDetail(ReviewRunSummary):
    label: str | None
    results: list[ObjectResultItem] = Field(
        description="Stored results; empty unless the run completed. Never carries SQL text."
    )


class FalsePositiveUpdate(BaseModel):
    false_positive: StrictBool


class FalsePositiveState(BaseModel):
    id: str
    false_positive: bool
    changed_at: datetime | None


class DeletedRuns(BaseModel):
    deleted_count: int
