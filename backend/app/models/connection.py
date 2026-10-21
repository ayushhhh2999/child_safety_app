from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Connection(Base):
    __tablename__ = "connections"
    __table_args__ = (
        UniqueConstraint(
            "first_user_id",
            "second_user_id",
            name="uq_connections_user_pair",
        ),
        CheckConstraint(
            "first_user_id < second_user_id",
            name="ck_connections_canonical_user_order",
        ),
        CheckConstraint(
            "requester_id != recipient_id",
            name="ck_connections_distinct_participants",
        ),
        CheckConstraint(
            "(requester_id = first_user_id OR requester_id = second_user_id) "
            "AND (recipient_id = first_user_id OR recipient_id = second_user_id)",
            name="ck_connections_request_participants",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'disconnected')",
            name="ck_connections_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    first_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    second_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    requester_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class SharingPermission(Base):
    __tablename__ = "sharing_permissions"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "owner_id",
            name="uq_sharing_permissions_connection_owner",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    share_location: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    share_app_usage: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    share_restriction_alerts: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
