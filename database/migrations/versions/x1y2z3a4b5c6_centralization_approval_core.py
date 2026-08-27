"""Centralization approval core tables.

Revision ID: x1y2z3a4b5c6
Revises: w9x0y1z2a3b4
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "x1y2z3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "w9x0y1z2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "change_requests",
        sa.Column("change_request_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("domain", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("proposer_user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("reviewer_user_id", sa.Integer(), sa.ForeignKey("users.user_id")),
        sa.Column("review_note", sa.Text()),
        sa.Column("conflict_explanation", sa.Text()),
        sa.Column("base_revision", sa.String(64)),
        sa.Column("impact_summary", postgresql.JSONB()),
        sa.Column("request_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("change_requests.change_request_id")),
        sa.Column("idempotency_key", sa.String(128), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "change_operations",
        sa.Column("change_operation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("change_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("change_requests.change_request_id"), nullable=False),
        sa.Column("operation_order", sa.Integer(), nullable=False),
        sa.Column("entity_kind", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(128)),
        sa.Column("operation_type", sa.String(32), nullable=False),
        sa.Column("base_row_version", sa.Integer()),
        sa.Column("before_state", postgresql.JSONB()),
        sa.Column("after_state", postgresql.JSONB()),
        sa.Column("validation_result", postgresql.JSONB()),
        sa.Column("payload_version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("change_request_id", "operation_order", name="uq_change_op_order"),
    )
    op.create_table(
        "audit_events",
        sa.Column("audit_event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("users.user_id")),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_kind", sa.String(64)),
        sa.Column("entity_id", sa.String(128)),
        sa.Column("change_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("change_requests.change_request_id")),
        sa.Column("correlation_id", sa.String(64)),
        sa.Column("before_json", postgresql.JSONB()),
        sa.Column("after_json", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "user_permissions",
        sa.Column("user_permission_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("permission_code", sa.String(64), nullable=False),
        sa.UniqueConstraint("user_id", "permission_code", name="uq_user_permission"),
    )
    op.create_table(
        "jobs",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("idempotency_key", sa.String(128), unique=True),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("lease_owner", sa.String(64)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "outbox_events",
        sa.Column("outbox_event_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("outbox_events")
    op.drop_table("jobs")
    op.drop_table("user_permissions")
    op.drop_table("audit_events")
    op.drop_table("change_operations")
    op.drop_table("change_requests")
