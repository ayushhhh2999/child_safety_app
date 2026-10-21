"""Add owner-scoped location, activity, and restriction records.

Revision ID: 0003_tracking_data
Revises: 0002_login_throttling
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_tracking_data"
down_revision = "0002_login_throttling"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "location_updates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("accuracy_meters", sa.Float(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_location_updates_owner_id", "location_updates", ["owner_id"])
    op.create_index(
        "ix_location_updates_recorded_at", "location_updates", ["recorded_at"]
    )

    op.create_table(
        "app_activity_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("package_name", sa.String(length=255), nullable=False),
        sa.Column("app_name", sa.String(length=120), nullable=False),
        sa.Column("event_type", sa.String(length=10), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_app_activity_events_owner_id", "app_activity_events", ["owner_id"]
    )
    op.create_index(
        "ix_app_activity_events_recorded_at",
        "app_activity_events",
        ["recorded_at"],
    )

    op.create_table(
        "restricted_apps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("package_name", sa.String(length=255), nullable=False),
        sa.Column("app_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_restricted_apps_owner_id", "restricted_apps", ["owner_id"]
    )

    op.create_table(
        "restriction_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("package_name", sa.String(length=255), nullable=False),
        sa.Column("app_name", sa.String(length=120), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_restriction_alerts_owner_id", "restriction_alerts", ["owner_id"]
    )
    op.create_index(
        "ix_restriction_alerts_recorded_at", "restriction_alerts", ["recorded_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_restriction_alerts_recorded_at", table_name="restriction_alerts")
    op.drop_index("ix_restriction_alerts_owner_id", table_name="restriction_alerts")
    op.drop_table("restriction_alerts")
    op.drop_index("ix_restricted_apps_owner_id", table_name="restricted_apps")
    op.drop_table("restricted_apps")
    op.drop_index(
        "ix_app_activity_events_recorded_at", table_name="app_activity_events"
    )
    op.drop_index(
        "ix_app_activity_events_owner_id", table_name="app_activity_events"
    )
    op.drop_table("app_activity_events")
    op.drop_index("ix_location_updates_recorded_at", table_name="location_updates")
    op.drop_index("ix_location_updates_owner_id", table_name="location_updates")
    op.drop_table("location_updates")
