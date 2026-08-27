"""Staged import lineage tables."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "z3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "y2z3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "source_files",
        sa.Column("source_file_id", sa.UUID(), primary_key=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("active_version_id", sa.UUID()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "source_file_versions",
        sa.Column("source_file_version_id", sa.UUID(), primary_key=True),
        sa.Column("source_file_id", sa.UUID(), sa.ForeignKey("source_files.source_file_id"), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("mime_type", sa.String(128)),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.user_id")),
        sa.Column("supersedes_version_id", sa.UUID()),
        sa.Column("parse_status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("checksum_sha256", "category", name="uq_source_version_checksum_category"),
    )
    op.create_table(
        "import_runs",
        sa.Column("import_run_id", sa.UUID(), primary_key=True),
        sa.Column(
            "source_file_version_id",
            sa.UUID(),
            sa.ForeignKey("source_file_versions.source_file_version_id"),
            nullable=False,
        ),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="staged"),
        sa.Column("change_request_id", sa.UUID(), sa.ForeignKey("change_requests.change_request_id")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.user_id")),
        sa.Column("row_counts", sa.JSON()),
        sa.Column("validation_summary", sa.JSON()),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("category", "checksum_sha256", name="uq_import_run_category_checksum"),
    )
    op.create_table(
        "import_issues",
        sa.Column("import_issue_id", sa.UUID(), primary_key=True),
        sa.Column("import_run_id", sa.UUID(), sa.ForeignKey("import_runs.import_run_id"), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context", sa.JSON()),
    )


def downgrade() -> None:
    op.drop_table("import_issues")
    op.drop_table("import_runs")
    op.drop_table("source_file_versions")
    op.drop_table("source_files")
