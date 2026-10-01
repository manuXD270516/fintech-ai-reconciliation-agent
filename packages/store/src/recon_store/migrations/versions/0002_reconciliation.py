"""M2 deterministic reconciliation: artifacts, rejections, runs, results and inbox.

Revision ID: 0002_reconciliation
Revises: 0001_transaction_domain
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision = "0002_reconciliation"
down_revision = "0001_transaction_domain"
branch_labels = None
depends_on = None

S = "recon"


def upgrade() -> None:
    op.add_column(
        "reconciliation_batches",
        sa.Column("left_complete", sa.Boolean, nullable=False, server_default=sa.text("false")),
        schema=S,
    )
    op.add_column(
        "reconciliation_batches",
        sa.Column("right_complete", sa.Boolean, nullable=False, server_default=sa.text("false")),
        schema=S,
    )

    op.create_table(
        "source_artifacts",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("provider_id", sa.String(128), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("row_count", sa.Integer, nullable=False),
        sa.Column("accepted", sa.Integer, nullable=False),
        sa.Column("duplicates", sa.Integer, nullable=False),
        sa.Column("conflicts", sa.Integer, nullable=False),
        sa.Column("rejected", sa.Integer, nullable=False),
        sa.Column("received_by", sa.String(128), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "source", "provider_id", "idempotency_key", name="uq_artifact_idempotency"
        ),
        schema=S,
    )

    op.create_table(
        "ingestion_rejections",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "artifact_id", sa.BigInteger, sa.ForeignKey(f"{S}.source_artifacts.id"), nullable=False
        ),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("provider_id", sa.String(128), nullable=False),
        sa.Column("row_number", sa.Integer, nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("message", sa.String(300), nullable=False),
        sa.Column("payment_ref", sa.String(128)),
        sa.Column("merchant_account", sa.String(128)),
        sa.Column("currency", sa.String(3)),
        sa.Column("raw_hash", sa.String(64), nullable=False),
        schema=S,
    )
    op.create_index(
        "ix_rejection_scope",
        "ingestion_rejections",
        ["tenant_id", "provider_id", "merchant_account", "currency"],
        schema=S,
    )

    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("batch_id", sa.String(128), nullable=False),
        sa.Column("run_number", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("ruleset_version", sa.String(32), nullable=False),
        sa.Column("snapshot_hash", sa.String(64)),
        sa.Column("observation_count", sa.Integer),
        sa.Column("requested_by", sa.String(128), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("error", sa.String(300)),
        sa.UniqueConstraint("tenant_id", "batch_id", "run_number", name="uq_run_number"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "batch_id"],
            [f"{S}.reconciliation_batches.tenant_id", f"{S}.reconciliation_batches.batch_id"],
            name="fk_run_batch",
        ),
        sa.CheckConstraint("status IN ('requested', 'completed', 'failed')", name="ck_run_status"),
        schema=S,
    )

    op.create_table(
        "match_results",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("run_id", sa.Uuid, sa.ForeignKey(f"{S}.reconciliation_runs.id"), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("payment_ref", sa.String(128), nullable=False),
        sa.Column("operation_type", sa.String(32), nullable=False),
        sa.Column("match_status", sa.String(16), nullable=False),
        sa.Column("rule", sa.String(32), nullable=False),
        sa.Column("discrepancy_types", postgresql.ARRAY(sa.String(32)), nullable=False),
        sa.Column("left_ids", postgresql.ARRAY(sa.BigInteger), nullable=False),
        sa.Column("right_ids", postgresql.ARRAY(sa.BigInteger), nullable=False),
        sa.Column("amount_difference_minor", sa.BigInteger),
        sa.Column("score", sa.Numeric(6, 4)),
        sa.Column("alternatives", postgresql.ARRAY(sa.BigInteger), nullable=False),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_result_ordinal"),
        schema=S,
    )

    op.create_table(
        "inbox",
        sa.Column("consumer", sa.String(64), nullable=False),
        sa.Column("event_id", sa.Uuid, nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("consumer", "event_id", name="pk_inbox"),
        schema=S,
    )

    role = context.config.attributes["runtime_role"]
    for statement in (
        f'GRANT SELECT, INSERT ON {S}.source_artifacts TO "{role}"',
        f'GRANT SELECT, INSERT ON {S}.ingestion_rejections TO "{role}"',
        f'GRANT SELECT, INSERT ON {S}.reconciliation_runs TO "{role}"',
        f"GRANT UPDATE (status, snapshot_hash, observation_count, completed_at, error) "
        f'ON {S}.reconciliation_runs TO "{role}"',
        f'GRANT SELECT, INSERT ON {S}.match_results TO "{role}"',
        f'GRANT SELECT, INSERT ON {S}.inbox TO "{role}"',
    ):
        op.execute(statement)


def downgrade() -> None:
    for table in (
        "inbox",
        "match_results",
        "reconciliation_runs",
        "ingestion_rejections",
        "source_artifacts",
    ):
        op.drop_table(table, schema=S)
    op.drop_column("reconciliation_batches", "right_complete", schema=S)
    op.drop_column("reconciliation_batches", "left_complete", schema=S)
