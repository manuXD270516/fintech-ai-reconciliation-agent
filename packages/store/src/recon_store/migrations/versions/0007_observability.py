"""M9 observability: outbox trace context and service heartbeats.

Revision ID: 0007_observability
Revises: 0006_cases
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

revision = "0007_observability"
down_revision = "0006_cases"
branch_labels = None
depends_on = None

S = "recon"


def upgrade() -> None:
    op.add_column("outbox", sa.Column("trace_context", sa.String(128)), schema=S)
    op.create_table(
        "service_heartbeats",
        sa.Column("service", sa.String(64), primary_key=True),
        sa.Column("instance", sa.String(128), nullable=False),
        sa.Column("beat_at", sa.DateTime(timezone=True), nullable=False),
        schema=S,
    )
    role = context.config.attributes["runtime_role"]
    for statement in (
        f'GRANT SELECT, INSERT ON {S}.service_heartbeats TO "{role}"',
        f'GRANT UPDATE (instance, beat_at) ON {S}.service_heartbeats TO "{role}"',
    ):
        op.execute(statement)


def downgrade() -> None:
    op.drop_table("service_heartbeats", schema=S)
    op.drop_column("outbox", "trace_context", schema=S)
