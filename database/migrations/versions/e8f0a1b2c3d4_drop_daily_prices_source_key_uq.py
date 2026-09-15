"""Drop oversized daily_prices source_key unique index (free-tier DB size).

Revision ID: e8f0a1b2c3d4
Revises: d7e8f0a1b2c3
Create Date: 2026-09-15 15:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e8f0a1b2c3d4"
down_revision = "d7e8f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ~65MB on staging; uniqueness already covered by (security_id, trade_date, source).
    op.drop_constraint("uq_daily_prices_source_key", "daily_prices", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint("uq_daily_prices_source_key", "daily_prices", ["source_key"])
