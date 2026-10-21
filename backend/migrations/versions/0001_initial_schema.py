"""Create the initial user and connection schema.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=30), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_id", "users", ["id"], unique=False)
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("first_user_id", sa.Integer(), nullable=False),
        sa.Column("second_user_id", sa.Integer(), nullable=False),
        sa.Column("requester_id", sa.Integer(), nullable=False),
        sa.Column("recipient_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "first_user_id < second_user_id",
            name="ck_connections_canonical_user_order",
        ),
        sa.CheckConstraint(
            "requester_id != recipient_id",
            name="ck_connections_distinct_participants",
        ),
        sa.CheckConstraint(
            "(requester_id = first_user_id OR requester_id = second_user_id) "
            "AND (recipient_id = first_user_id OR recipient_id = second_user_id)",
            name="ck_connections_request_participants",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'disconnected')",
            name="ck_connections_status",
        ),
        sa.ForeignKeyConstraint(
            ["first_user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["second_user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recipient_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "first_user_id",
            "second_user_id",
            name="uq_connections_user_pair",
        ),
    )
    op.create_index("ix_connections_id", "connections", ["id"], unique=False)
    op.create_index(
        "ix_connections_first_user_id",
        "connections",
        ["first_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_connections_second_user_id",
        "connections",
        ["second_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_connections_status",
        "connections",
        ["status"],
        unique=False,
    )

    op.create_table(
        "sharing_permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("share_location", sa.Boolean(), nullable=False),
        sa.Column("share_app_usage", sa.Boolean(), nullable=False),
        sa.Column("share_restriction_alerts", sa.Boolean(), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["connections.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "owner_id",
            name="uq_sharing_permissions_connection_owner",
        ),
    )
    op.create_index(
        "ix_sharing_permissions_id",
        "sharing_permissions",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_sharing_permissions_connection_id",
        "sharing_permissions",
        ["connection_id"],
        unique=False,
    )
    op.create_index(
        "ix_sharing_permissions_owner_id",
        "sharing_permissions",
        ["owner_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sharing_permissions_owner_id",
        table_name="sharing_permissions",
    )
    op.drop_index(
        "ix_sharing_permissions_connection_id",
        table_name="sharing_permissions",
    )
    op.drop_index(
        "ix_sharing_permissions_id",
        table_name="sharing_permissions",
    )
    op.drop_table("sharing_permissions")
    op.drop_index("ix_connections_status", table_name="connections")
    op.drop_index(
        "ix_connections_second_user_id",
        table_name="connections",
    )
    op.drop_index(
        "ix_connections_first_user_id",
        table_name="connections",
    )
    op.drop_index("ix_connections_id", table_name="connections")
    op.drop_table("connections")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")
