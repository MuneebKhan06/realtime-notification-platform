"""create delivery log table

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-13

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "delivery_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instance_id", sa.String(length=100), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_delivery_log_notification_id", "delivery_log", ["notification_id"])


def downgrade() -> None:
    op.drop_index("idx_delivery_log_notification_id", table_name="delivery_log")
    op.drop_table("delivery_log")
