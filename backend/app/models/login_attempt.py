from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FailedLoginAttempt(Base):
    __tablename__ = "failed_login_attempts"
    __table_args__ = (
        Index("ix_failed_login_attempts_window_started_at", "window_started_at"),
    )

    bucket_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
