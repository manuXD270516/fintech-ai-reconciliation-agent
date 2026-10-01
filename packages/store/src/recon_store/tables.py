"""SQLAlchemy Core table definitions. Alembic migrations are the source of the schema;
`tests` compare both so they cannot drift."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Computed,
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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR

from recon_store.vector import Vector

SCHEMA = "recon"
metadata = MetaData(schema=SCHEMA)
# Python equivalent: recon_store.observations.transaction_uid().
TRANSACTION_UID_SQL = "md5(tenant_id || '|' || source || '|' || source_record_id)::uuid"

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
    # M4: stable opaque ID of the canonical observation (same for every revision of a key).
    Column("transaction_uid", Uuid, Computed(TRANSACTION_UID_SQL, persisted=True), nullable=False),
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
Index("ix_observation_uid", observations.c.tenant_id, observations.c.transaction_uid)

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

# --- M3 knowledge base (hybrid retrieval) ----------------------------------------
EMBEDDING_DIMENSIONS = 256

knowledge_documents = Table(
    "knowledge_documents",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("document_id", String(128), nullable=False),
    Column("version", Integer, nullable=False),
    Column("tenant_scope", String(128), nullable=False),
    Column("acl", ARRAY(String(32)), nullable=False),
    Column("provider_id", String(128)),
    Column("document_type", String(32), nullable=False),
    Column("title", String(300), nullable=False),
    Column("language", String(8), nullable=False),
    Column("source_uri", String(300), nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("effective_from", DateTime(timezone=True), nullable=False),
    Column("effective_to", DateTime(timezone=True)),
    Column("published_at", DateTime(timezone=True), nullable=False),
    Column("ingested_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("review_status", String(16), nullable=False),
    Column("synthetic", Boolean, nullable=False),
    Column("supersedes", String(160)),
    Column("index_version", String(64), nullable=False),
    UniqueConstraint("document_id", "version", name="uq_knowledge_document_version"),
    CheckConstraint(
        "review_status IN ('published', 'draft', 'revoked')", name="ck_knowledge_review_status"
    ),
    CheckConstraint(
        "effective_to IS NULL OR effective_to > effective_from", name="ck_knowledge_validity"
    ),
)

knowledge_chunks = Table(
    "knowledge_chunks",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("document_pk", BigInteger, ForeignKey("recon.knowledge_documents.id"), nullable=False),
    Column("chunk_id", String(64), nullable=False),
    Column("section_slug", String(160), nullable=False),
    Column("section_path", String(400), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("start_line", Integer, nullable=False),
    Column("end_line", Integer, nullable=False),
    Column("token_count", Integer, nullable=False),
    Column("error_codes", ARRAY(String(16)), nullable=False),
    Column("flagged_instructions", Boolean, nullable=False),
    Column("content", Text, nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("fts_config", String(16), nullable=False),
    Column("tsv", TSVECTOR, nullable=False),
    Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=False),
    Column("embedding_model", String(64), nullable=False),
    Column("embedding_revision", String(32), nullable=False),
    Column("dimensions", SmallInteger, nullable=False),
    UniqueConstraint("chunk_id", name="uq_knowledge_chunk_id"),
    CheckConstraint("fts_config IN ('spanish', 'english')", name="ck_knowledge_fts_config"),
)
Index("ix_knowledge_chunks_tsv", knowledge_chunks.c.tsv, postgresql_using="gin")
Index("ix_knowledge_chunks_codes", knowledge_chunks.c.error_codes, postgresql_using="gin")

# --- M4 synthetic provider status snapshots (read by get_provider_status) -----------
provider_status = Table(
    "provider_status_snapshots",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("provider_id", String(128), nullable=False),
    Column("status", String(32), nullable=False),
    Column("valid_from", DateTime(timezone=True), nullable=False),
    Column("valid_to", DateTime(timezone=True)),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    Column("details", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("source_version", String(64), nullable=False),
    UniqueConstraint("provider_id", "valid_from", name="uq_provider_status_validity"),
    CheckConstraint(
        "status IN ('operational', 'degraded', 'outage')", name="ck_provider_status_value"
    ),
    CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="ck_provider_status_window"),
)

# --- M5 investigations (persisted state machine records) --------------------------
investigations = Table(
    "investigations",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", String(128), nullable=False),
    Column("case_ref", String(128), nullable=False),
    Column("run_id", Uuid, ForeignKey("recon.reconciliation_runs.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("case_version", Integer, nullable=False),
    Column("input_snapshot_hash", String(64), nullable=False),
    Column("state", String(16), nullable=False),
    Column("requested_by", String(128), nullable=False),
    Column("correlation_id", String(64), nullable=False),
    Column("record", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    UniqueConstraint(
        "tenant_id", "case_ref", "input_snapshot_hash", name="uq_investigation_per_snapshot"
    ),
    CheckConstraint(
        "state IN ('REQUESTED', 'NOT_NEEDED', 'PLANNED', 'EXECUTED', 'DRAFTED', 'ABSTAINED', "
        "'ESCALATED', 'FAILED')",
        name="ck_investigation_state",
    ),
)

# --- M6 case management and human approval -----------------------------------------
cases = Table(
    "cases",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", String(128), nullable=False),
    Column("case_ref", String(128), nullable=False),
    Column("run_id", Uuid, ForeignKey("recon.reconciliation_runs.id"), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("status", String(24), nullable=False),
    Column("version", Integer, nullable=False),
    Column("opened_by", String(128), nullable=False),
    Column("closed_reason", String(500)),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    UniqueConstraint("tenant_id", "case_ref", name="uq_case_ref"),
    CheckConstraint("version >= 1", name="ck_case_version"),
    CheckConstraint(
        "status IN ('OPEN', 'HUMAN_REVIEW', 'APPROVED', 'REJECTED', 'NEEDS_INFORMATION', 'CLOSED')",
        name="ck_case_status",
    ),
)

recommendations = Table(
    "recommendations",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("case_id", Uuid, ForeignKey("recon.cases.id"), nullable=False),
    Column("tenant_id", String(128), nullable=False),
    Column("case_version", Integer, nullable=False),
    Column("proposer", String(128), nullable=False),
    Column("action", String(32), nullable=False),
    Column("rationale", String(2000), nullable=False),
    Column("investigation_id", Uuid, ForeignKey("recon.investigations.id")),
    Column("investigation_requester", String(128)),
    Column("review_result", String(24), nullable=False),
    Column("evidence", JSONB, nullable=False),
    Column("status", String(16), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    CheckConstraint(
        "status IN ('PENDING', 'APPROVED', 'REJECTED', 'NEEDS_INFORMATION', 'SUPERSEDED', "
        "'OBSOLETE')",
        name="ck_recommendation_status",
    ),
)

decisions = Table(
    "decisions",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("case_id", Uuid, ForeignKey("recon.cases.id"), nullable=False),
    Column("recommendation_id", Uuid, ForeignKey("recon.recommendations.id"), nullable=False),
    Column("tenant_id", String(128), nullable=False),
    Column("approver", String(128), nullable=False),
    Column("role", String(32), nullable=False),
    Column("decision", String(24), nullable=False),
    Column("reason", String(2000), nullable=False),
    Column("case_version", Integer, nullable=False),
    Column("idempotency_key", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    UniqueConstraint("tenant_id", "idempotency_key", name="uq_decision_idempotency"),
    UniqueConstraint("recommendation_id", name="uq_decision_per_recommendation"),
)
