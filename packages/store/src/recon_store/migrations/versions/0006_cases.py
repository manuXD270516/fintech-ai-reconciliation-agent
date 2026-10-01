"""M6 case management and human approval: cases, recommendations and decisions.

Revision ID: 0006_cases
Revises: 0005_investigations
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision = "0006_cases"
down_revision = "0005_investigations"
branch_labels = None
depends_on = None

S = "recon"
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "cases",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("case_ref", sa.String(128), nullable=False),
        sa.Column("run_id", sa.Uuid, sa.ForeignKey(f"{S}.reconciliation_runs.id"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("opened_by", sa.String(128), nullable=False),
        sa.Column("closed_reason", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("tenant_id", "case_ref", name="uq_case_ref"),
        sa.CheckConstraint("version >= 1", name="ck_case_version"),
        sa.CheckConstraint(
            "status IN ('OPEN', 'HUMAN_REVIEW', 'APPROVED', 'REJECTED', 'NEEDS_INFORMATION', "
            "'CLOSED')",
            name="ck_case_status",
        ),
        schema=S,
    )
    op.create_table(
        "recommendations",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("case_id", sa.Uuid, sa.ForeignKey(f"{S}.cases.id"), nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("case_version", sa.Integer, nullable=False),
        sa.Column("proposer", sa.String(128), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("rationale", sa.String(2000), nullable=False),
        sa.Column("investigation_id", sa.Uuid, sa.ForeignKey(f"{S}.investigations.id")),
        sa.Column("investigation_requester", sa.String(128)),
        sa.Column("review_result", sa.String(24), nullable=False),
        sa.Column("evidence", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED', 'NEEDS_INFORMATION', 'SUPERSEDED', "
            "'OBSOLETE')",
            name="ck_recommendation_status",
        ),
        schema=S,
    )
    op.create_table(
        "decisions",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("case_id", sa.Uuid, sa.ForeignKey(f"{S}.cases.id"), nullable=False),
        sa.Column(
            "recommendation_id", sa.Uuid, sa.ForeignKey(f"{S}.recommendations.id"), nullable=False
        ),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("approver", sa.String(128), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("case_version", sa.Integer, nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_decision_idempotency"),
        sa.UniqueConstraint("recommendation_id", name="uq_decision_per_recommendation"),
        schema=S,
    )
    role = context.config.attributes["runtime_role"]
    for statement in (
        f'GRANT SELECT, INSERT ON {S}.cases TO "{role}"',
        f'GRANT UPDATE (status, version, closed_reason, updated_at) ON {S}.cases TO "{role}"',
        f'GRANT SELECT, INSERT ON {S}.recommendations TO "{role}"',
        f'GRANT UPDATE (status) ON {S}.recommendations TO "{role}"',
        f'GRANT SELECT, INSERT ON {S}.decisions TO "{role}"',
    ):
        op.execute(statement)


def downgrade() -> None:
    for table in ("decisions", "recommendations", "cases"):
        op.drop_table(table, schema=S)
