import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.database import Base
from app.main import health
from app.models.login_attempt import FailedLoginAttempt
from app.services.login_throttle import record_login_attempt


class ProductionConfigurationTests(unittest.TestCase):
    def test_production_requires_a_strong_explicit_secret(self) -> None:
        config = Settings()
        config.APP_ENV = "production"
        config.JWT_SECRET_KEY = "too-short"
        config.DATABASE_URL = "postgresql+psycopg://user:password@db/app"

        with self.assertRaisesRegex(RuntimeError, "at least 32 bytes"):
            config.validate_startup()

    def test_production_rejects_sqlite(self) -> None:
        config = Settings()
        config.APP_ENV = "production"
        config.JWT_SECRET_KEY = "a" * 48
        config.DATABASE_URL = "sqlite:///./mobile_tracker.db"

        with self.assertRaisesRegex(RuntimeError, "requires PostgreSQL"):
            config.validate_startup()

    def test_production_rejects_example_secret(self) -> None:
        config = Settings()
        config.APP_ENV = "production"
        config.JWT_SECRET_KEY = "replace-this-with-a-real-secret-value"
        config.DATABASE_URL = "postgresql+psycopg://user:password@db/app"

        with self.assertRaisesRegex(RuntimeError, "Replace the example"):
            config.validate_startup()

    def test_production_accepts_postgresql_and_a_strong_secret(self) -> None:
        config = Settings()
        config.APP_ENV = "production"
        config.JWT_SECRET_KEY = "a" * 48
        config.DATABASE_URL = "postgresql+psycopg://user:password@db/app"

        config.validate_startup()


class LoginThrottleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.old_limit = settings.LOGIN_RATE_LIMIT_ATTEMPTS
        self.old_window = settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS
        settings.LOGIN_RATE_LIMIT_ATTEMPTS = 2
        settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS = 60

    def tearDown(self) -> None:
        settings.LOGIN_RATE_LIMIT_ATTEMPTS = self.old_limit
        settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS = self.old_window
        self.db.close()
        self.engine.dispose()

    def test_limits_attempts_resets_after_window_and_stores_only_digest(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)

        self.assertEqual(record_login_attempt(self.db, "known_user", now), (True, 0))
        self.assertEqual(record_login_attempt(self.db, "known_user", now), (True, 0))
        allowed, retry_after = record_login_attempt(self.db, "known_user", now)
        self.assertFalse(allowed)
        self.assertEqual(retry_after, 60)

        row = self.db.scalar(select(FailedLoginAttempt))
        self.assertIsNotNone(row)
        self.assertNotIn("known_user", row.bucket_digest)
        self.assertEqual(row.attempts, 3)

        later = now + timedelta(seconds=61)
        self.assertEqual(
            record_login_attempt(self.db, "known_user", later),
            (True, 0),
        )
        self.assertEqual(
            record_login_attempt(self.db, "different_user", later),
            (True, 0),
        )


class HealthCheckTests(unittest.TestCase):
    def test_health_check_confirms_database_connectivity(self) -> None:
        engine = create_engine("sqlite://")
        try:
            with patch("app.main.engine", engine):
                self.assertEqual(
                    health(),
                    {"status": "healthy", "database": "available"},
                )
        finally:
            engine.dispose()

    def test_health_check_reports_database_failure(self) -> None:
        class BrokenEngine:
            def connect(self):
                raise OperationalError(
                    "SELECT 1",
                    {},
                    RuntimeError("connection refused"),
                )

        with patch("app.main.engine", BrokenEngine()):
            with self.assertRaises(HTTPException) as error:
                health()
        self.assertEqual(error.exception.status_code, 503)
