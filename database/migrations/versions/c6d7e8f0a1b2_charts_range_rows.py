"""Charts Range row canonical store and working-view overlays."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c6d7e8f0a1b2"
down_revision: Union[str, Sequence[str], None] = "b5c6d7e8f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "charts_range_rows",
        sa.Column("excel_row", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("section", sa.String(16), nullable=False, server_default="holdings"),
        sa.Column("high", sa.Numeric(20, 4)),
        sa.Column("low", sa.Numeric(20, 4)),
        sa.Column("close_override", sa.Numeric(20, 4)),
        sa.Column("weekly_close", sa.Numeric(20, 4)),
        sa.Column("support_resistance", sa.Text()),
        sa.Column("weekly_close_date", sa.String(32)),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.Integer()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("charts_range_rows")
