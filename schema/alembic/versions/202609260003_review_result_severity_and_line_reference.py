"""Rule-result severity only for FAIL verdicts; line references up to 500 characters.

sql-review/PRDs/003-object-review Requirement 11 and 13: the parser keeps line references of up to
500 characters (a comma list of lines can be long) and only a FAIL verdict has a severity. Rows
written before this revision keep their severity only when their status is FAIL.

Revision ID: 202609260003
Revises: 202609260002
Create Date: 2026-09-26 16:56:06.077584
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "202609260003"
down_revision: str | None = "202609260002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "review_finding",
        "line_reference",
        existing_type=sa.VARCHAR(length=64),
        type_=sa.String(length=500),
        existing_comment="Line reference in the original text, for example 'Satır 12' or 'Satır 12–15'; empty when none could be derived.",
        existing_nullable=True,
    )
    op.alter_column(
        "review_rule_result",
        "severity",
        existing_type=sa.VARCHAR(length=8),
        nullable=True,
        comment="Severity of a FAIL verdict; code reflection app.domain.models.review.Severity: 'HIGH', 'MEDIUM', 'LOW'. Empty for every other status.",
        existing_comment="Severity; code reflection app.domain.models.review.Severity: 'HIGH', 'MEDIUM', 'LOW'. Critical rules report HIGH, normal rules LOW; an invalid model value becomes LOW.",
    )
    op.alter_column(
        "review_rule_result",
        "line_reference",
        existing_type=sa.VARCHAR(length=64),
        type_=sa.String(length=500),
        existing_comment="Line reference in the original text, for example 'Satır 12' or 'Satır 12–15'; empty when none could be derived.",
        existing_nullable=True,
    )
    op.execute("UPDATE review_rule_result SET severity = NULL WHERE status <> 'FAIL'")
    op.create_check_constraint(
        op.f("ck_review_rule_result_severity_only_for_fail"),
        "review_rule_result",
        "(status = 'FAIL') = (severity IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_review_rule_result_severity_only_for_fail"), "review_rule_result", type_="check"
    )
    op.execute(
        "UPDATE review_rule_result SET severity = CASE priority_group WHEN 'critical' "
        "THEN 'HIGH' ELSE 'LOW' END WHERE severity IS NULL"
    )
    op.execute("UPDATE review_rule_result SET line_reference = left(line_reference, 64)")
    op.execute("UPDATE review_finding SET line_reference = left(line_reference, 64)")
    op.alter_column(
        "review_rule_result",
        "line_reference",
        existing_type=sa.String(length=500),
        type_=sa.VARCHAR(length=64),
        existing_comment="Line reference in the original text, for example 'Satır 12' or 'Satır 12–15'; empty when none could be derived.",
        existing_nullable=True,
    )
    op.alter_column(
        "review_rule_result",
        "severity",
        existing_type=sa.VARCHAR(length=8),
        nullable=False,
        comment="Severity; code reflection app.domain.models.review.Severity: 'HIGH', 'MEDIUM', 'LOW'. Critical rules report HIGH, normal rules LOW; an invalid model value becomes LOW.",
        existing_comment="Severity of a FAIL verdict; code reflection app.domain.models.review.Severity: 'HIGH', 'MEDIUM', 'LOW'. Empty for every other status.",
    )
    op.alter_column(
        "review_finding",
        "line_reference",
        existing_type=sa.String(length=500),
        type_=sa.VARCHAR(length=64),
        existing_comment="Line reference in the original text, for example 'Satır 12' or 'Satır 12–15'; empty when none could be derived.",
        existing_nullable=True,
    )
