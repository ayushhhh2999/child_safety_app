"""Persist login throttling across application workers.

Revision ID: 0002_login_throttling
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_login_throttling"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "failed_login_attempts",
        sa.Column("bucket_digest", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("bucket_digest"),
    )
    op.create_index(
        "ix_failed_login_attempts_window_started_at",
        "failed_login_attempts",
        ["window_started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_failed_login_attempts_window_started_at",
        table_name="failed_login_attempts",
    )
    op.drop_table("failed_login_attempts")
