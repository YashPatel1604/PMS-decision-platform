"""Client positions for approval workflow."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "y2z3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "x1y2z3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_positions",
        sa.Column("client_position_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("book", sa.String(16), nullable=False, server_default="client"),
        sa.Column("symbol", sa.String(64), nullable=False),
        sa.Column("qty", sa.Numeric(20, 4), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.Integer()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("book", "symbol", name="uq_client_positions_book_symbol"),
    )


def downgrade() -> None:
    op.drop_table("client_positions")
