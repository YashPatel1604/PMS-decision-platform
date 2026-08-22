"""Add diagnostics JSON to watchlist_member_metrics for v2.0 provenance.

Revision ID: s5t6u7v8w9x0
Revises: r4a5b6c7d8e9
Create Date: 2026-08-22 13:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "s5t6u7v8w9x0"
down_revision: Union[str, Sequence[str], None] = "r4a5b6c7d8e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "watchlist_member_metrics",
        sa.Column(
            "diagnostics",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("watchlist_member_metrics", "diagnostics")
