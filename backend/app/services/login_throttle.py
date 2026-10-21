import hashlib
import hmac
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.login_attempt import FailedLoginAttempt


_RECORD_ATTEMPT = text(
    """
    INSERT INTO failed_login_attempts
        (bucket_digest, attempts, window_started_at)
    VALUES (:bucket_digest, 1, :now)
    ON CONFLICT (bucket_digest) DO UPDATE SET
        attempts = CASE
            WHEN failed_login_attempts.window_started_at <= :cutoff THEN 1
            ELSE failed_login_attempts.attempts + 1
        END,
        window_started_at = CASE
            WHEN failed_login_attempts.window_started_at <= :cutoff THEN :now
            ELSE failed_login_attempts.window_started_at
        END
    """
)


def _bucket_digest(identifier: str) -> str:
    secret = settings.JWT_SECRET_KEY
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY is not configured")
    return hmac.new(
        secret.encode("utf-8"),
        identifier.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def record_login_attempt(
    db: Session,
    identifier: str,
    now: datetime | None = None,
) -> tuple[bool, int]:
    dialect = db.get_bind().dialect.name
    if dialect not in {"postgresql", "sqlite"}:
        raise RuntimeError(
            f"Login throttling does not support database dialect: {dialect}"
        )

    now = now or datetime.now(timezone.utc)
    window = timedelta(seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS)
    cutoff = now - window
    digest = _bucket_digest(identifier)

    db.execute(
        _RECORD_ATTEMPT,
        {
            "bucket_digest": digest,
            "now": now,
            "cutoff": cutoff,
        },
    )
    db.execute(
        text(
            "DELETE FROM failed_login_attempts "
            "WHERE window_started_at < :oldest"
        ),
        {"oldest": now - (window * 2)},
    )
    db.commit()

    attempt = db.scalar(
        select(FailedLoginAttempt)
        .where(FailedLoginAttempt.bucket_digest == digest)
        .execution_options(populate_existing=True)
    )
    if attempt is None:
        raise RuntimeError("Failed to persist login attempt")

    if attempt.attempts <= settings.LOGIN_RATE_LIMIT_ATTEMPTS:
        return True, 0

    started_at = attempt.window_started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    retry_after = max(
        1,
        math.ceil((started_at + window - now).total_seconds()),
    )
    return False, retry_after


def clear_login_attempts(db: Session, identifier: str) -> None:
    db.execute(
        text(
            "DELETE FROM failed_login_attempts "
            "WHERE bucket_digest = :bucket_digest"
        ),
        {"bucket_digest": _bucket_digest(identifier)},
    )
    db.commit()
