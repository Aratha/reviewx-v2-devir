"""Remove the 50-object upper limit of a review run.

A run has no object limit any more; the check keeps only "at least one object". Expand-only: the
constraint is relaxed, no row changes, and the previous application version keeps working with
this schema because it enforces its own limit before it writes. Downgrade refuses while a run
with more than 50 objects is stored, because the previous check would reject it.

Spec: sql-review/PRDs/003-object-review (Veri ve geçiş, Decision 3).

Revision ID: 202610020001
Revises: 202610010002
Create Date: 2026-10-02 09:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202610020001"
down_revision: str | None = "202610010002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "review_run",
        "object_count",
        existing_type=sa.INTEGER(),
        comment="Number of selected objects, at least 1; always 1 for a script run.",
        existing_comment="Number of selected objects, 1 to 50; always 1 for a script run.",
        existing_nullable=False,
    )
    op.drop_constraint(op.f("ck_review_run_object_count_range"), "review_run", type_="check")
    op.create_check_constraint(
        op.f("ck_review_run_object_count_positive"), "review_run", "object_count >= 1"
    )


def downgrade() -> None:
    larger = op.get_bind().execute(
        sa.text("SELECT count(*) FROM review_run WHERE object_count > 50")
    )
    if larger.scalar():
        raise RuntimeError(
            "review_run holds runs with more than 50 objects; delete them before downgrading, "
            "because the previous schema allows at most 50 objects in a run"
        )
    op.drop_constraint(op.f("ck_review_run_object_count_positive"), "review_run", type_="check")
    op.create_check_constraint(
        op.f("ck_review_run_object_count_range"),
        "review_run",
        "object_count BETWEEN 1 AND 50",
    )
    op.alter_column(
        "review_run",
        "object_count",
        existing_type=sa.INTEGER(),
        comment="Number of selected objects, 1 to 50; always 1 for a script run.",
        existing_comment="Number of selected objects, at least 1; always 1 for a script run.",
        existing_nullable=False,
    )
