"""M1 transaction domain: observations, batches, audit and outbox.

Revision ID: 0001_transaction_domain
Revises:
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

revision = "0001_transaction_domain"
down_revision = None
branch_labels = None
depends_on = None

S = "recon"


def _ts(name: str, nullable: bool = False, now: bool = False) -> sa.Column[datetime]:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=sa.text("now()") if now else None,
    )


def upgrade() -> None:
    op.create_table(
        "transaction_observations",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_record_id", sa.String(128), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("provider_id", sa.String(128), nullable=False),
        sa.Column("merchant_account", sa.String(128), nullable=False),
        sa.Column("operation_type", sa.String(32), nullable=False),
        sa.Column("payment_ref", sa.String(128), nullable=False),
        sa.Column("attempt_ref", sa.String(128)),
        sa.Column("amount_minor", sa.BigInteger, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("currency_exponent", sa.SmallInteger, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        _ts("occurred_at"),
        sa.Column("occurred_offset_minutes", sa.SmallInteger, nullable=False),
        _ts("received_at"),
        sa.Column("received_offset_minutes", sa.SmallInteger, nullable=False),
        _ts("effective_at", nullable=True),
        sa.Column("effective_offset_minutes", sa.SmallInteger),
        sa.Column("raw_hash", sa.String(64), nullable=False),
        sa.Column("normalization_version", sa.String(64), nullable=False),
        _ts("recorded_at", now=True),
        sa.UniqueConstraint(
            "tenant_id", "source", "source_record_id", "revision", name="uq_observation_revision"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_observation_revision_positive"),
        sa.CheckConstraint(
            "source IN ('internal_ledger', 'provider_report')", name="ck_observation_source"
        ),
        sa.CheckConstraint("currency_exponent BETWEEN 0 AND 4", name="ck_observation_exponent"),
        sa.CheckConstraint("raw_hash ~ '^[0-9a-f]{64}$'", name="ck_observation_raw_hash"),
        sa.CheckConstraint(
            "(effective_at IS NULL) = (effective_offset_minutes IS NULL)",
            name="ck_observation_effective_pair",
        ),
        schema=S,
    )
    op.create_index(
        "ix_observation_scope_ref",
        "transaction_observations",
        ["tenant_id", "provider_id", "merchant_account", "payment_ref"],
        schema=S,
    )

    op.create_table(
        "reconciliation_batches",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("batch_id", sa.String(128), nullable=False),
        sa.Column("provider_id", sa.String(128), nullable=False),
        sa.Column("merchant_account", sa.String(128), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        _ts("window_start"),
        _ts("window_end"),
        sa.Column("business_timezone", sa.String(64), nullable=False),
        sa.Column("left_source", sa.String(32), nullable=False),
        sa.Column("right_source", sa.String(32), nullable=False),
        _ts("cutoff_at"),
        sa.Column("version", sa.Integer, nullable=False, server_default=sa.text("1")),
        _ts("created_at", now=True),
        sa.UniqueConstraint("tenant_id", "batch_id", name="uq_batch"),
        sa.CheckConstraint("window_end > window_start", name="ck_batch_window"),
        sa.CheckConstraint("cutoff_at >= window_end", name="ck_batch_cutoff"),
        sa.CheckConstraint("left_source <> right_source", name="ck_batch_sources"),
        schema=S,
    )

    op.create_table(
        "audit_entries",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        _ts("occurred_at", now=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(256), nullable=False),
        sa.Column("resource_version", sa.Integer),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema=S,
    )

    op.create_table(
        "outbox",
        sa.Column("event_id", sa.Uuid, primary_key=True),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("aggregate_id", sa.String(256), nullable=False),
        sa.Column("aggregate_version", sa.Integer, nullable=False),
        _ts("occurred_at", now=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("causation_id", sa.String(64)),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        _ts("published_at", nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text),
        schema=S,
    )
    op.create_index(
        "ix_outbox_unpublished",
        "outbox",
        ["occurred_at"],
        schema=S,
        postgresql_where=sa.text("published_at IS NULL"),
    )

    role = context.config.attributes["runtime_role"]
    for statement in (
        f"REVOKE ALL ON SCHEMA {S} FROM PUBLIC",
        f'GRANT USAGE ON SCHEMA {S} TO "{role}"',
        # Observations and audit are append-only for the runtime role.
        f'GRANT SELECT, INSERT ON {S}.transaction_observations TO "{role}"',
        f'GRANT SELECT, INSERT ON {S}.audit_entries TO "{role}"',
        f'GRANT SELECT, INSERT, UPDATE ON {S}.reconciliation_batches TO "{role}"',
        f'GRANT SELECT, INSERT ON {S}.outbox TO "{role}"',
        f'GRANT UPDATE (published_at, attempts, last_error) ON {S}.outbox TO "{role}"',
    ):
        op.execute(statement)


def downgrade() -> None:
    for table in ("outbox", "audit_entries", "reconciliation_batches", "transaction_observations"):
        op.drop_table(table, schema=S)
