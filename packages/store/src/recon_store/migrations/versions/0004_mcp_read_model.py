"""M4 read model for fintech-mcp-server: stable transaction IDs, provider status, MCP role.

Revision ID: 0004_mcp_read_model
Revises: 0003_knowledge
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision = "0004_mcp_read_model"
down_revision = "0003_knowledge"
branch_labels = None
depends_on = None

S = "recon"
UID_SQL = "md5(tenant_id || '|' || source || '|' || source_record_id)::uuid"
MCP_READ_TABLES = (
    "transaction_observations",
    "reconciliation_batches",
    "reconciliation_runs",
    "match_results",
    "knowledge_documents",
    "knowledge_chunks",
    "provider_status_snapshots",
)


def upgrade() -> None:
    op.add_column(
        "transaction_observations",
        sa.Column("transaction_uid", sa.Uuid, sa.Computed(UID_SQL, persisted=True), nullable=False),
        schema=S,
    )
    op.create_index(
        "ix_observation_uid",
        "transaction_observations",
        ["tenant_id", "transaction_uid"],
        schema=S,
    )
    op.create_table(
        "provider_status_snapshots",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("provider_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("source_version", sa.String(64), nullable=False),
        sa.UniqueConstraint("provider_id", "valid_from", name="uq_provider_status_validity"),
        sa.CheckConstraint(
            "status IN ('operational', 'degraded', 'outage')", name="ck_provider_status_value"
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_to > valid_from", name="ck_provider_status_window"
        ),
        schema=S,
    )

    runtime = context.config.attributes["runtime_role"]
    mcp = context.config.attributes["mcp_role"]
    statements = [
        f'GRANT SELECT, INSERT ON {S}.provider_status_snapshots TO "{runtime}"',
        # The MCP identity reads evidence and appends audit; it cannot write business data.
        f'GRANT USAGE ON SCHEMA {S} TO "{mcp}"',
        f'GRANT INSERT ON {S}.audit_entries TO "{mcp}"',
    ]
    statements += [f'GRANT SELECT ON {S}.{table} TO "{mcp}"' for table in MCP_READ_TABLES]
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("provider_status_snapshots", schema=S)
    op.drop_index("ix_observation_uid", "transaction_observations", schema=S)
    op.drop_column("transaction_observations", "transaction_uid", schema=S)
