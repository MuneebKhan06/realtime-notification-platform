"""create read receipts table

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-13

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "read_receipts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_read_receipts_notification_id", "read_receipts", ["notification_id"])
    op.create_index("idx_read_receipts_user_id", "read_receipts", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_read_receipts_user_id", table_name="read_receipts")
    op.drop_index("idx_read_receipts_notification_id", table_name="read_receipts")
    op.drop_table("read_receipts")
