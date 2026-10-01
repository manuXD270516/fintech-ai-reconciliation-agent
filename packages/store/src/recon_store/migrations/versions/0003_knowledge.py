"""M3 hybrid knowledge base: versioned documents and chunks with tsvector + pgvector.

Revision ID: 0003_knowledge
Revises: 0002_reconciliation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

from recon_store.vector import Vector

revision = "0003_knowledge"
down_revision = "0002_reconciliation"
branch_labels = None
depends_on = None

S = "recon"
DIMENSIONS = 256


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("document_id", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("tenant_scope", sa.String(128), nullable=False),
        sa.Column("acl", postgresql.ARRAY(sa.String(32)), nullable=False),
        sa.Column("provider_id", sa.String(128)),
        sa.Column("document_type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("source_uri", sa.String(300), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("review_status", sa.String(16), nullable=False),
        sa.Column("synthetic", sa.Boolean, nullable=False),
        sa.Column("supersedes", sa.String(160)),
        sa.Column("index_version", sa.String(64), nullable=False),
        sa.UniqueConstraint("document_id", "version", name="uq_knowledge_document_version"),
        sa.CheckConstraint(
            "review_status IN ('published', 'draft', 'revoked')",
            name="ck_knowledge_review_status",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from", name="ck_knowledge_validity"
        ),
        schema=S,
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column(
            "document_pk",
            sa.BigInteger,
            sa.ForeignKey(f"{S}.knowledge_documents.id"),
            nullable=False,
        ),
        sa.Column("chunk_id", sa.String(64), nullable=False),
        sa.Column("section_slug", sa.String(160), nullable=False),
        sa.Column("section_path", sa.String(400), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("start_line", sa.Integer, nullable=False),
        sa.Column("end_line", sa.Integer, nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("error_codes", postgresql.ARRAY(sa.String(16)), nullable=False),
        sa.Column("flagged_instructions", sa.Boolean, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("fts_config", sa.String(16), nullable=False),
        sa.Column("tsv", postgresql.TSVECTOR, nullable=False),
        sa.Column("embedding", Vector(DIMENSIONS), nullable=False),
        sa.Column("embedding_model", sa.String(64), nullable=False),
        sa.Column("embedding_revision", sa.String(32), nullable=False),
        sa.Column("dimensions", sa.SmallInteger, nullable=False),
        sa.UniqueConstraint("chunk_id", name="uq_knowledge_chunk_id"),
        sa.CheckConstraint("fts_config IN ('spanish', 'english')", name="ck_knowledge_fts_config"),
        schema=S,
    )
    op.create_index(
        "ix_knowledge_chunks_tsv",
        "knowledge_chunks",
        ["tsv"],
        schema=S,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_knowledge_chunks_codes",
        "knowledge_chunks",
        ["error_codes"],
        schema=S,
        postgresql_using="gin",
    )

    role = context.config.attributes["runtime_role"]
    for statement in (
        f'GRANT SELECT, INSERT ON {S}.knowledge_documents TO "{role}"',
        f'GRANT UPDATE (review_status) ON {S}.knowledge_documents TO "{role}"',
        f'GRANT SELECT, INSERT ON {S}.knowledge_chunks TO "{role}"',
    ):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("knowledge_chunks", schema=S)
    op.drop_table("knowledge_documents", schema=S)
