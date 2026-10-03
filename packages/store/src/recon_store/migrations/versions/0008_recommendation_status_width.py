"""Fix: recommendations.status fits NEEDS_INFORMATION (17 chars; the column was 16).

Revision ID: 0008_recommendation_status_width
Revises: 0007_observability
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_recommendation_status_width"
down_revision = "0007_observability"
branch_labels = None
depends_on = None

S = "recon"


def upgrade() -> None:
    op.alter_column(
        "recommendations",
        "status",
        type_=sa.String(24),
        existing_type=sa.String(16),
        existing_nullable=False,
        schema=S,
    )


def downgrade() -> None:
    op.alter_column(
        "recommendations",
        "status",
        type_=sa.String(16),
        existing_type=sa.String(24),
        existing_nullable=False,
        schema=S,
    )
