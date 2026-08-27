"""Client position canonical fields and per-book bank balance."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7e8f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c6d7e8f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("client_positions", sa.Column("mcap_factor", sa.Numeric(20, 8), nullable=True))
    op.add_column("client_positions", sa.Column("index_label", sa.String(128), nullable=True))
    op.create_table(
        "client_book_settings",
        sa.Column("book", sa.String(16), primary_key=True),
        sa.Column("bank_balance", sa.Numeric(20, 4), nullable=True),
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
    op.drop_table("client_book_settings")
    op.drop_column("client_positions", "index_label")
    op.drop_column("client_positions", "mcap_factor")
