"""SQLAlchemy Core table definitions. Alembic migrations are the source of the schema;
`tests` compare both so they cannot drift."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    MetaData,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

SCHEMA = "recon"
metadata = MetaData(schema=SCHEMA)

observations = Table(
    "transaction_observations",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("tenant_id", String(128), nullable=False),
    Column("source", String(32), nullable=False),
    Column("source_record_id", String(128), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("provider_id", String(128), nullable=False),
    Column("merchant_account", String(128), nullable=False),
    Column("operation_type", String(32), nullable=False),
    Column("payment_ref", String(128), nullable=False),
    Column("attempt_ref", String(128)),
    Column("amount_minor", BigInteger, nullable=False),
    Column("currency", String(3), nullable=False),
    Column("currency_exponent", SmallInteger, nullable=False),
    Column("status", String(32), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("occurred_offset_minutes", SmallInteger, nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False),
    Column("received_offset_minutes", SmallInteger, nullable=False),
    Column("effective_at", DateTime(timezone=True)),
    Column("effective_offset_minutes", SmallInteger),
    Column("raw_hash", String(64), nullable=False),
    Column("normalization_version", String(64), nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    UniqueConstraint(
        "tenant_id", "source", "source_record_id", "revision", name="uq_observation_revision"
    ),
    CheckConstraint("revision >= 1", name="ck_observation_revision_positive"),
    CheckConstraint(
        "source IN ('internal_ledger', 'provider_report')", name="ck_observation_source"
    ),
    CheckConstraint("currency_exponent BETWEEN 0 AND 4", name="ck_observation_exponent"),
    CheckConstraint("raw_hash ~ '^[0-9a-f]{64}$'", name="ck_observation_raw_hash"),
    CheckConstraint(
        "(effective_at IS NULL) = (effective_offset_minutes IS NULL)",
        name="ck_observation_effective_pair",
    ),
)
Index(
    "ix_observation_scope_ref",
    observations.c.tenant_id,
    observations.c.provider_id,
    observations.c.merchant_account,
    observations.c.payment_ref,
)

batches = Table(
    "reconciliation_batches",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("tenant_id", String(128), nullable=False),
    Column("batch_id", String(128), nullable=False),
    Column("provider_id", String(128), nullable=False),
    Column("merchant_account", String(128), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("window_start", DateTime(timezone=True), nullable=False),
    Column("window_end", DateTime(timezone=True), nullable=False),
    Column("business_timezone", String(64), nullable=False),
    Column("left_source", String(32), nullable=False),
    Column("right_source", String(32), nullable=False),
    Column("cutoff_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False, server_default=text("1")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("left_complete", Boolean, nullable=False, server_default=text("false")),
    Column("right_complete", Boolean, nullable=False, server_default=text("false")),
    UniqueConstraint("tenant_id", "batch_id", name="uq_batch"),
    CheckConstraint("window_end > window_start", name="ck_batch_window"),
    CheckConstraint("cutoff_at >= window_end", name="ck_batch_cutoff"),
    CheckConstraint("left_source <> right_source", name="ck_batch_sources"),
)

audit_entries = Table(
    "audit_entries",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("tenant_id", String(128), nullable=False),
    Column("actor", String(128), nullable=False),
    Column("action", String(64), nullable=False),
    Column("resource_type", String(64), nullable=False),
    Column("resource_id", String(256), nullable=False),
    Column("resource_version", Integer),
    Column("outcome", String(32), nullable=False),
    Column("correlation_id", String(64), nullable=False),
    Column("details", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
)

outbox = Table(
    "outbox",
    metadata,
    Column("event_id", Uuid, primary_key=True),
    Column("event_type", String(128), nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("tenant_id", String(128), nullable=False),
    Column("aggregate_id", String(256), nullable=False),
    Column("aggregate_version", Integer, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("correlation_id", String(64), nullable=False),
    Column("causation_id", String(64)),
    Column("payload", JSONB, nullable=False),
    Column("published_at", DateTime(timezone=True)),
    Column("attempts", Integer, nullable=False, server_default=text("0")),
    Column("last_error", Text),
)
Index(
    "ix_outbox_unpublished",
    outbox.c.occurred_at,
    postgresql_where=outbox.c.published_at.is_(None),
)

artifacts = Table(
    "source_artifacts",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("tenant_id", String(128), nullable=False),
    Column("source", String(32), nullable=False),
    Column("provider_id", String(128), nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("parser_version", String(64), nullable=False),
    Column("row_count", Integer, nullable=False),
    Column("accepted", Integer, nullable=False),
    Column("duplicates", Integer, nullable=False),
    Column("conflicts", Integer, nullable=False),
    Column("rejected", Integer, nullable=False),
    Column("received_by", String(128), nullable=False),
    Column("received_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("correlation_id", String(64), nullable=False),
    UniqueConstraint(
        "tenant_id", "source", "provider_id", "idempotency_key", name="uq_artifact_idempotency"
    ),
)

rejections = Table(
    "ingestion_rejections",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("artifact_id", BigInteger, ForeignKey("recon.source_artifacts.id"), nullable=False),
    Column("tenant_id", String(128), nullable=False),
    Column("source", String(32), nullable=False),
    Column("provider_id", String(128), nullable=False),
    Column("row_number", Integer, nullable=False),
    Column("code", String(32), nullable=False),
    Column("message", String(300), nullable=False),
    Column("payment_ref", String(128)),
    Column("merchant_account", String(128)),
    Column("currency", String(3)),
    Column("raw_hash", String(64), nullable=False),
)
Index(
    "ix_rejection_scope",
    rejections.c.tenant_id,
    rejections.c.provider_id,
    rejections.c.merchant_account,
    rejections.c.currency,
)

runs = Table(
    "reconciliation_runs",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", String(128), nullable=False),
    Column("batch_id", String(128), nullable=False),
    Column("run_number", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("ruleset_version", String(32), nullable=False),
    Column("snapshot_hash", String(64)),
    Column("observation_count", Integer),
    Column("requested_by", String(128), nullable=False),
    Column("requested_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("completed_at", DateTime(timezone=True)),
    Column("correlation_id", String(64), nullable=False),
    Column("error", String(300)),
    UniqueConstraint("tenant_id", "batch_id", "run_number", name="uq_run_number"),
    ForeignKeyConstraint(
        ["tenant_id", "batch_id"],
        ["recon.reconciliation_batches.tenant_id", "recon.reconciliation_batches.batch_id"],
        name="fk_run_batch",
    ),
    CheckConstraint("status IN ('requested', 'completed', 'failed')", name="ck_run_status"),
)

results = Table(
    "match_results",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("run_id", Uuid, ForeignKey("recon.reconciliation_runs.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("payment_ref", String(128), nullable=False),
    Column("operation_type", String(32), nullable=False),
    Column("match_status", String(16), nullable=False),
    Column("rule", String(32), nullable=False),
    Column("discrepancy_types", ARRAY(String(32)), nullable=False),
    Column("left_ids", ARRAY(BigInteger), nullable=False),
    Column("right_ids", ARRAY(BigInteger), nullable=False),
    Column("amount_difference_minor", BigInteger),
    Column("score", Numeric(6, 4)),
    Column("alternatives", ARRAY(BigInteger), nullable=False),
    Column("explanation", Text, nullable=False),
    UniqueConstraint("run_id", "ordinal", name="uq_result_ordinal"),
)

inbox = Table(
    "inbox",
    metadata,
    Column("consumer", String(64), nullable=False),
    Column("event_id", Uuid, nullable=False),
    Column("processed_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    PrimaryKeyConstraint("consumer", "event_id", name="pk_inbox"),
)
