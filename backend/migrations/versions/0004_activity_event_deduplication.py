"""Add stable keys to deduplicate synced activity events.

Revision ID: 0004_activity_event_deduplication
Revises: 0003_tracking_data
"""
from alembic import op
import sqlalchemy as sa
from hashlib import sha256


revision = "0004_activity_event_deduplication"
down_revision = "0003_tracking_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "app_activity_events",
        sa.Column("event_key", sa.String(length=64), nullable=True),
    )
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, owner_id, package_name, event_type, recorded_at "
            "FROM app_activity_events"
        )
    )
    for row in rows:
        event_key = sha256(f"legacy|{row.id}".encode("utf-8")).hexdigest()
        connection.execute(
            sa.text(
                "UPDATE app_activity_events SET event_key = :event_key "
                "WHERE id = :event_id"
            ),
            {"event_key": event_key, "event_id": row.id},
        )

    with op.batch_alter_table("app_activity_events") as batch_op:
        batch_op.alter_column(
            "event_key",
            existing_type=sa.String(length=64),
            nullable=False,
        )
        batch_op.create_unique_constraint(
            "uq_app_activity_events_owner_event_key",
            ["owner_id", "event_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("app_activity_events") as batch_op:
        batch_op.drop_constraint(
            "uq_app_activity_events_owner_event_key",
            type_="unique",
        )
        batch_op.drop_column("event_key")
