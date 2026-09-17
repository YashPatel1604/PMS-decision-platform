"""Add research document index, answer cache, goals, and audit tables.

Revision ID: x0y1z2a3b4c5
Revises: w9x0y1z2a3b4
Create Date: 2026-09-17 20:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "x0y1z2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "e8f0a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_documents",
        sa.Column("document_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_root", sa.String(length=32), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=True),
        sa.Column("mtime_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("parse_status", sa.String(length=16), nullable=False),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.Column("security_id", sa.String(length=16), nullable=True),
        sa.ForeignKeyConstraint(["security_id"], ["securities.security_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("document_id"),
        sa.UniqueConstraint("source_root", "relative_path", name="uq_research_doc_path"),
    )
    op.create_index("ix_research_documents_content_hash", "research_documents", ["content_hash"])
    op.create_index("ix_research_documents_security_id", "research_documents", ["security_id"])

    op.create_table(
        "research_document_pages",
        sa.Column("page_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["research_documents.document_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("page_id"),
        sa.UniqueConstraint("document_id", "page_number", name="uq_research_page"),
    )
    op.create_index(
        "ix_research_document_pages_document_id", "research_document_pages", ["document_id"]
    )

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            ALTER TABLE research_document_pages
            ADD COLUMN tsv tsvector
            GENERATED ALWAYS AS (to_tsvector('english', coalesce(text, ''))) STORED
            """
        )
        op.execute(
            "CREATE INDEX ix_research_document_pages_tsv ON research_document_pages USING GIN (tsv)"
        )

    op.create_table(
        "research_answer_cache",
        sa.Column("cache_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("security_id", sa.String(length=16), nullable=True),
        sa.Column("request_kind", sa.String(length=32), nullable=False),
        sa.Column("response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("citation_page_ids", sa.JSON(), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("token_in", sa.Integer(), nullable=True),
        sa.Column("token_out", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["security_id"], ["securities.security_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("cache_id"),
        sa.UniqueConstraint("cache_key"),
    )
    op.create_index(
        "ix_research_answer_cache_security_id", "research_answer_cache", ["security_id"]
    )

    op.create_table(
        "research_goals",
        sa.Column("goal_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("security_id", sa.String(length=16), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("source_cache_id", sa.Integer(), nullable=True),
        sa.Column("created_by_user", sa.String(length=128), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["source_cache_id"], ["research_answer_cache.cache_id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("goal_id"),
    )
    op.create_index("ix_research_goals_security_id", "research_goals", ["security_id"])

    op.create_table(
        "research_query_audit",
        sa.Column("audit_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("request_kind", sa.String(length=32), nullable=False),
        sa.Column("security_id", sa.String(length=16), nullable=True),
        sa.Column("cache_hit", sa.Boolean(), nullable=False),
        sa.Column("token_in", sa.Integer(), nullable=True),
        sa.Column("token_out", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("audit_id"),
    )


def downgrade() -> None:
    op.drop_table("research_query_audit")
    op.drop_table("research_goals")
    op.drop_index("ix_research_answer_cache_security_id", table_name="research_answer_cache")
    op.drop_table("research_answer_cache")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_research_document_pages_tsv")
    op.drop_index("ix_research_document_pages_document_id", table_name="research_document_pages")
    op.drop_table("research_document_pages")
    op.drop_index("ix_research_documents_security_id", table_name="research_documents")
    op.drop_index("ix_research_documents_content_hash", table_name="research_documents")
    op.drop_table("research_documents")
