"""Investment theses + portfolio surveillance events.

Revision ID: f9a0b1c2d3e4
Revises: x0y1z2a3b4c5
Create Date: 2026-09-18 02:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, Sequence[str], None] = "x0y1z2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "investment_theses",
        sa.Column("thesis_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("security_id", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("thesis_summary", sa.Text(), nullable=True),
        sa.Column("business_quality", sa.Text(), nullable=True),
        sa.Column("industry_thesis", sa.Text(), nullable=True),
        sa.Column("competitive_advantage", sa.Text(), nullable=True),
        sa.Column("management_thesis", sa.Text(), nullable=True),
        sa.Column("capital_allocation_thesis", sa.Text(), nullable=True),
        sa.Column("revenue_assumption", sa.Text(), nullable=True),
        sa.Column("margin_assumption", sa.Text(), nullable=True),
        sa.Column("earnings_assumption", sa.Text(), nullable=True),
        sa.Column("valuation_framework", sa.Text(), nullable=True),
        sa.Column("expected_holding_period", sa.Text(), nullable=True),
        sa.Column("bull_case", sa.Text(), nullable=True),
        sa.Column("base_case", sa.Text(), nullable=True),
        sa.Column("bear_case", sa.Text(), nullable=True),
        sa.Column("key_risks", sa.Text(), nullable=True),
        sa.Column("key_monitoring_variables", sa.Text(), nullable=True),
        sa.Column("disconfirming_evidence", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["security_id"], ["securities.security_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("thesis_id"),
        sa.UniqueConstraint("security_id", "version", name="uq_investment_thesis_version"),
    )
    op.create_index("ix_investment_theses_security_id", "investment_theses", ["security_id"])
    op.create_index("ix_investment_theses_status", "investment_theses", ["status"])

    op.create_table(
        "portfolio_events",
        sa.Column("event_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("security_id", sa.String(length=16), nullable=True),
        sa.Column("company", sa.Text(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_document_reference", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("materiality", sa.String(length=16), nullable=False),
        sa.Column("materiality_reason", sa.Text(), nullable=False),
        sa.Column("affected_thesis", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(length=16), nullable=True),
        sa.Column("universe", sa.String(length=16), nullable=False, server_default="other"),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["security_id"], ["securities.security_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint("dedupe_key", name="uq_portfolio_events_dedupe"),
    )
    op.create_index("ix_portfolio_events_security_id", "portfolio_events", ["security_id"])
    op.create_index("ix_portfolio_events_materiality", "portfolio_events", ["materiality"])
    op.create_index("ix_portfolio_events_event_date", "portfolio_events", ["event_date"])

    op.create_table(
        "thesis_conflict_flags",
        sa.Column("flag_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("thesis_id", sa.Integer(), nullable=False),
        sa.Column("security_id", sa.String(length=16), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=True),
        sa.Column("assumption_affected", sa.Text(), nullable=False),
        sa.Column("what_changed", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("management_explanation", sa.Text(), nullable=True),
        sa.Column("investigate_next", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["thesis_id"], ["investment_theses.thesis_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["security_id"], ["securities.security_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["event_id"], ["portfolio_events.event_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("flag_id"),
    )
    op.create_index("ix_thesis_conflict_flags_security_id", "thesis_conflict_flags", ["security_id"])
    op.create_index("ix_thesis_conflict_flags_status", "thesis_conflict_flags", ["status"])


def downgrade() -> None:
    op.drop_index("ix_thesis_conflict_flags_status", table_name="thesis_conflict_flags")
    op.drop_index("ix_thesis_conflict_flags_security_id", table_name="thesis_conflict_flags")
    op.drop_table("thesis_conflict_flags")
    op.drop_index("ix_portfolio_events_event_date", table_name="portfolio_events")
    op.drop_index("ix_portfolio_events_materiality", table_name="portfolio_events")
    op.drop_index("ix_portfolio_events_security_id", table_name="portfolio_events")
    op.drop_table("portfolio_events")
    op.drop_index("ix_investment_theses_status", table_name="investment_theses")
    op.drop_index("ix_investment_theses_security_id", table_name="investment_theses")
    op.drop_table("investment_theses")
