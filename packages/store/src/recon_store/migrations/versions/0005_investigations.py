"""M5 investigations: persisted state machine records (drafts without operational effect).

Revision ID: 0005_investigations
Revises: 0004_mcp_read_model
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision = "0005_investigations"
down_revision = "0004_mcp_read_model"
branch_labels = None
depends_on = None

S = "recon"


def upgrade() -> None:
    op.create_table(
        "investigations",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("case_ref", sa.String(128), nullable=False),
        sa.Column("run_id", sa.Uuid, sa.ForeignKey(f"{S}.reconciliation_runs.id"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("case_version", sa.Integer, nullable=False),
        sa.Column("input_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column(
            "record", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id", "case_ref", "input_snapshot_hash", name="uq_investigation_per_snapshot"
        ),
        sa.CheckConstraint(
            "state IN ('REQUESTED', 'NOT_NEEDED', 'PLANNED', 'EXECUTED', 'DRAFTED', 'ABSTAINED', "
            "'ESCALATED', 'FAILED')",
            name="ck_investigation_state",
        ),
        schema=S,
    )
    role = context.config.attributes["runtime_role"]
    for statement in (
        f'GRANT SELECT, INSERT ON {S}.investigations TO "{role}"',
        f'GRANT UPDATE (state, record, updated_at) ON {S}.investigations TO "{role}"',
    ):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("investigations", schema=S)
