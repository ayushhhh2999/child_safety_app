import os
import secrets
from urllib.parse import urlsplit


class Settings:
    def __init__(self) -> None:
        self.APP_NAME = "Mobile Tracker API"
        self.APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
        self.DATABASE_URL = os.getenv(
            "DATABASE_URL",
            "sqlite:///./mobile_tracker.db",
        )
        self.JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
        if not self.JWT_SECRET_KEY and self.APP_ENV != "production":
            self.JWT_SECRET_KEY = secrets.token_urlsafe(48)
        self.JWT_ALGORITHM = "HS256"
        self.ACCESS_TOKEN_EXPIRE_MINUTES = 30
        self.LOGIN_RATE_LIMIT_ATTEMPTS = int(
            os.getenv("LOGIN_RATE_LIMIT_ATTEMPTS", "5")
        )
        self.LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(
            os.getenv("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "900")
        )

    def validate_startup(self) -> None:
        if self.APP_ENV not in {"development", "test", "production"}:
            raise RuntimeError(
                "APP_ENV must be development, test, or production"
            )

        if not self.JWT_SECRET_KEY or len(self.JWT_SECRET_KEY.encode("utf-8")) < 32:
            raise RuntimeError("JWT_SECRET_KEY must contain at least 32 bytes")

        if self.LOGIN_RATE_LIMIT_ATTEMPTS < 1:
            raise RuntimeError("LOGIN_RATE_LIMIT_ATTEMPTS must be positive")
        if self.LOGIN_RATE_LIMIT_WINDOW_SECONDS < 1:
            raise RuntimeError("LOGIN_RATE_LIMIT_WINDOW_SECONDS must be positive")

        if self.APP_ENV == "production":
            if "replace" in self.JWT_SECRET_KEY.lower():
                raise RuntimeError(
                    "Replace the example JWT_SECRET_KEY before production startup"
                )
            if urlsplit(self.DATABASE_URL).scheme not in {
                "postgresql",
                "postgresql+psycopg",
            }:
                raise RuntimeError(
                    "Production requires PostgreSQL via DATABASE_URL"
                )


settings = Settings()
