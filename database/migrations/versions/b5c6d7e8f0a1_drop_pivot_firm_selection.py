"""Drop unused pivot_firm_selection (selection stays in browser localStorage)."""

from typing import Sequence, Union

from alembic import op

revision: str = "b5c6d7e8f0a1"
down_revision: Union[str, Sequence[str], None] = "a4b5c6d7e8f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("pivot_firm_selection")


def downgrade() -> None:
    import sqlalchemy as sa

    op.create_table(
        "pivot_firm_selection",
        sa.Column("symbol", sa.String(64), primary_key=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
    )
