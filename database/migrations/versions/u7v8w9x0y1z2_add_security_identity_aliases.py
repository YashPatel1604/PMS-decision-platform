"""Add security_identity_aliases for historical watchlist identity.

Revision ID: u7v8w9x0y1z2
Revises: t6u7v8w9x0y1
Create Date: 2026-08-22 15:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "u7v8w9x0y1z2"
down_revision: Union[str, Sequence[str], None] = "t6u7v8w9x0y1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "security_identity_aliases",
        sa.Column("alias_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("security_id", sa.String(length=16), nullable=False),
        sa.Column("alias_name", sa.String(length=256), nullable=True),
        sa.Column("alias_type", sa.String(length=32), nullable=False),
        sa.Column("alias_value", sa.String(length=256), nullable=False),
        sa.Column("relationship_type", sa.String(length=32), nullable=False),
        sa.Column("historical_nse_symbol", sa.String(length=32), nullable=True),
        sa.Column("historical_bse_code", sa.String(length=16), nullable=True),
        sa.Column("historical_isin", sa.String(length=16), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="watchlist_seed"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["security_id"], ["securities.security_id"]),
        sa.PrimaryKeyConstraint("alias_id"),
        sa.UniqueConstraint(
            "alias_type",
            "alias_value",
            "relationship_type",
            name="uq_security_identity_aliases_key",
        ),
    )


def downgrade() -> None:
    op.drop_table("security_identity_aliases")
