from hashlib import sha256
import json
import logging
import os
import socket
import ssl
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

import certifi

from api_config import DEFAULT_API_BASE_URL


logger = logging.getLogger(__name__)
NETWORK_TIMEOUT_SECONDS = 20


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    def __init__(self) -> None:
        self.token: str | None = None
        self.on_unauthorized: Callable[[], None] | None = None
        self._executor = ThreadPoolExecutor(max_workers=3)
        self.base_url = self._load_base_url()

    @staticmethod
    def _normalize_base_url(value: str) -> str:
        url = value.strip().rstrip("/")
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("API URL must start with http:// or https://")
        if parsed.username or parsed.password:
            raise ValueError("Do not include credentials in the API URL")
        if parsed.query or parsed.fragment:
            raise ValueError("API URL cannot contain a query or fragment")
        return url

    def _load_base_url(self) -> str:
        if self._is_android():
            return self._normalize_base_url(DEFAULT_API_BASE_URL)

        configured = (
            os.environ.get("API_BASE_URL")
            or os.environ.get("MOBILE_TRACKER_API_URL")
        )
        if configured:
            return self._normalize_base_url(configured)

        try:
            from kivy.app import App

            app = App.get_running_app()
            if app is not None:
                saved = app.user_data_dir
                config_path = os.path.join(saved, "api_url.txt")
                try:
                    with open(config_path, encoding="utf-8") as config_file:
                        return self._normalize_base_url(config_file.read())
                except FileNotFoundError:
                    pass
        except ImportError:
            return ""

        from api_config import API_BASE_URL

        return self._normalize_base_url(API_BASE_URL) if API_BASE_URL else ""

    def set_base_url(self, value: str) -> None:
        normalized = self._normalize_base_url(value)
        if self._is_android() and normalized != DEFAULT_API_BASE_URL:
            raise ValueError(f"This Android build uses {DEFAULT_API_BASE_URL}.")
        from kivy.app import App

        app = App.get_running_app()
        if app is not None:
            config_path = os.path.join(app.user_data_dir, "api_url.txt")
            with open(config_path, "w", encoding="utf-8") as config_file:
                config_file.write(normalized)
        if normalized != self.base_url:
            self.logout()
        self.base_url = normalized

    @staticmethod
    def _is_android() -> bool:
        try:
            from kivy.utils import platform

            return platform == "android"
        except ImportError:
            return sys.platform == "android"

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _expect_object(value: Any, fields: dict[str, type]) -> dict[str, Any]:
        if not isinstance(value, dict) or any(
            type(value.get(key)) is not expected_type
            for key, expected_type in fields.items()
        ):
            raise ApiError("The API returned an unexpected response.")
        return value

    @staticmethod
    def _expect_list(value: Any) -> list[Any]:
        if not isinstance(value, list):
            raise ApiError("The API returned an unexpected response.")
        return value

    @classmethod
    def _expect_user(cls, value: Any) -> dict[str, Any]:
        return cls._expect_object(
            value,
            {"id": int, "username": str, "email": str},
        )

    def run_async(
        self,
        operation: Callable[[], Any],
        callback: Callable[[Any, Exception | None], None],
    ) -> Future[Any]:
        future = self._executor.submit(operation)

        def finish(result: Future[Any]) -> None:
            try:
                value = result.result()
                callback(value, None)
            except Exception as error:
                callback(None, error)

        future.add_done_callback(finish)
        return future

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
    ) -> Any:
        if not self.base_url:
            raise ApiError("Configure the API_BASE_URL before signing in.")
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        headers = {"Accept": "application/json"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = Request(url, data=body, headers=headers, method=method)
        tls_context = ssl.create_default_context(cafile=certifi.where())
        try:
            with urlopen(
                request,
                timeout=NETWORK_TIMEOUT_SECONDS,
                context=tls_context,
            ) as response:
                if response.status == 204:
                    return None
                response_body = response.read()
                if not response_body:
                    return None
                try:
                    return json.loads(response_body)
                except (json.JSONDecodeError, UnicodeDecodeError) as error:
                    logger.warning(
                        "API returned invalid JSON method=%s path=%s error=%s",
                        method,
                        path,
                        type(error).__name__,
                    )
                    raise ApiError("The API returned invalid JSON.") from error
        except HTTPError as error:
            logger.warning(
                "API returned HTTP error method=%s path=%s status=%s",
                method,
                path,
                error.code,
            )
            if error.code == 401 and self.token:
                self.logout()
                if self.on_unauthorized:
                    self.on_unauthorized()
            try:
                details = json.loads(error.read())
                message = details.get("detail", "The server rejected the request.")
            except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                message = "The server rejected the request."
            raise ApiError(
                f"{error.code}: {message}",
                status_code=error.code,
            ) from error
        except URLError as error:
            reason = error.reason
            if isinstance(reason, socket.gaierror):
                message = (
                    "Could not resolve the API server name. "
                    "Check your network or DNS."
                )
            elif isinstance(reason, (TimeoutError, socket.timeout)):
                message = "The API connection timed out. Please try again."
            elif isinstance(reason, ssl.SSLError):
                message = "Could not establish a secure connection to the API."
            elif isinstance(reason, ConnectionError):
                message = "Could not connect to the API server."
            else:
                message = "Could not reach the API. Check the network connection."
            logger.warning(
                "API network failure method=%s path=%s cause=%s details=%s",
                method,
                path,
                type(reason).__name__,
                reason,
            )
            raise ApiError(message) from error
        except (socket.gaierror, ssl.SSLError, ConnectionError) as error:
            if isinstance(error, socket.gaierror):
                message = (
                    "Could not resolve the API server name. "
                    "Check your network or DNS."
                )
            elif isinstance(error, ssl.SSLError):
                message = "Could not establish a secure connection to the API."
            else:
                message = "Could not connect to the API server."
            logger.warning(
                "API network failure method=%s path=%s cause=%s details=%s",
                method,
                path,
                type(error).__name__,
                error,
            )
            raise ApiError(message) from error
        except (TimeoutError, socket.timeout) as error:
            logger.warning(
                "API timeout method=%s path=%s timeout_seconds=%s cause=%s",
                method,
                path,
                NETWORK_TIMEOUT_SECONDS,
                type(error).__name__,
            )
            raise ApiError(
                "The API connection timed out. Please try again."
            ) from error

    def signup(self, username: str, email: str, password: str) -> dict[str, Any]:
        result = self._request(
            "POST",
            "/api/auth/signup",
            {"username": username, "email": email, "password": password},
        )
        return self._expect_user(result)

    def login(self, username: str, password: str) -> dict[str, Any]:
        result = self._request(
            "POST",
            "/api/auth/login",
            {"username": username, "password": password},
        )
        result = self._expect_object(
            result,
            {"access_token": str, "token_type": str},
        )
        if not result["access_token"] or result["token_type"].lower() != "bearer":
            raise ApiError("The API returned an invalid access token.")
        self.token = result["access_token"]
        try:
            return self._expect_user(self._request("GET", "/api/auth/me"))
        except ApiError:
            self.logout()
            raise

    def logout(self) -> None:
        self.token = None

    def health(self) -> dict[str, Any]:
        return self._expect_object(self._request("GET", "/health"), {"status": str})

    def search_user(self, username: str) -> dict[str, Any] | None:
        result = self._request(
            "GET",
            "/api/connections/search",
            query={"username": username},
        )
        if result is None:
            return None
        return self._expect_object(result, {"id": int, "username": str})

    def send_connection_request(self, username: str) -> dict[str, Any]:
        result = self._request(
            "POST",
            "/api/connections/request",
            {"username": username},
        )
        result = self._expect_object(
            result,
            {"id": int, "username": str, "direction": str, "created_at": str},
        )
        if result["direction"] != "outgoing":
            raise ApiError("The API returned an unexpected request direction.")
        return result

    def get_requests(self) -> list[dict[str, Any]]:
        requests = self._expect_list(self._request("GET", "/api/connections/requests"))
        for request in requests:
            self._expect_object(
                request,
                {"id": int, "username": str, "direction": str, "created_at": str},
            )
            if request["direction"] not in ("incoming", "outgoing"):
                raise ApiError("The API returned an unexpected request direction.")
        return requests

    def accept_request(self, connection_id: int) -> dict[str, Any]:
        result = self._request("POST", f"/api/connections/{connection_id}/accept")
        result = self._expect_object(
            result,
            {"id": int, "username": str, "status": str, "created_at": str},
        )
        if result["status"] != "accepted":
            raise ApiError("The API returned an unexpected connection status.")
        return result

    def reject_request(self, connection_id: int) -> dict[str, Any]:
        result = self._request("POST", f"/api/connections/{connection_id}/reject")
        result = self._expect_object(
            result,
            {"id": int, "username": str, "status": str, "created_at": str},
        )
        if result["status"] != "rejected":
            raise ApiError("The API returned an unexpected connection status.")
        return result

    def get_connections(self) -> list[dict[str, Any]]:
        connections = self._expect_list(self._request("GET", "/api/connections"))
        for connection in connections:
            self._expect_object(
                connection,
                {"id": int, "username": str, "status": str, "created_at": str},
            )
            if connection["status"] != "accepted":
                raise ApiError("The API returned an unexpected connection status.")
        return connections

    def get_permissions(self, connection_id: int) -> dict[str, Any]:
        result = self._request(
            "GET", f"/api/connections/{connection_id}/permissions"
        )
        return self._expect_object(
            result,
            {
                "share_location": bool,
                "share_app_usage": bool,
                "share_restriction_alerts": bool,
                "paused": bool,
            },
        )

    def update_permissions(
        self, connection_id: int, **updates: bool
    ) -> dict[str, Any]:
        result = self._request(
            "PATCH",
            f"/api/connections/{connection_id}/permissions",
            updates,
        )
        return self._expect_object(
            result,
            {
                "share_location": bool,
                "share_app_usage": bool,
                "share_restriction_alerts": bool,
                "paused": bool,
            },
        )

    def disconnect(self, connection_id: int) -> None:
        self._request("DELETE", f"/api/connections/{connection_id}")

    @classmethod
    def _expect_location(cls, value: Any) -> dict[str, Any]:
        location = cls._expect_object(
            value,
            {
                "id": int,
                "recorded_at": str,
            },
        )
        if any(
            isinstance(location.get(field), bool)
            or not isinstance(location.get(field), (int, float))
            for field in ("latitude", "longitude")
        ):
            raise ApiError("The API returned an unexpected location.")
        accuracy = location.get("accuracy_meters")
        if accuracy is not None and not isinstance(accuracy, (int, float)):
            raise ApiError("The API returned an unexpected location.")
        return location

    @classmethod
    def _expect_activity(cls, value: Any) -> dict[str, Any]:
        event = cls._expect_object(
            value,
            {
                "id": int,
                "package_name": str,
                "app_name": str,
                "event_type": str,
                "recorded_at": str,
            },
        )
        if event["event_type"] not in ("opened", "closed"):
            raise ApiError("The API returned an unexpected activity event.")
        return event

    def get_locations(self, limit: int = 50) -> list[dict[str, Any]]:
        values = self._expect_list(
            self._request("GET", "/api/locations/me", query={"limit": str(limit)})
        )
        return [self._expect_location(value) for value in values]

    def get_shared_locations(
        self, connection_id: int, limit: int = 50
    ) -> list[dict[str, Any]]:
        values = self._expect_list(
            self._request(
                "GET",
                f"/api/connections/{connection_id}/locations",
                query={"limit": str(limit)},
            )
        )
        return [self._expect_location(value) for value in values]

    def create_location(
        self,
        latitude: float,
        longitude: float,
        accuracy_meters: float | None,
        recorded_at: str,
    ) -> dict[str, Any]:
        result = self._request(
            "POST",
            "/api/locations",
            {
                "latitude": latitude,
                "longitude": longitude,
                "accuracy_meters": accuracy_meters,
                "recorded_at": recorded_at,
            },
        )
        return self._expect_location(result)

    def get_activities(self, limit: int = 50) -> list[dict[str, Any]]:
        values = self._expect_list(
            self._request("GET", "/api/activities/me", query={"limit": str(limit)})
        )
        return [self._expect_activity(value) for value in values]

    def get_shared_activities(
        self, connection_id: int, limit: int = 50
    ) -> list[dict[str, Any]]:
        values = self._expect_list(
            self._request(
                "GET",
                f"/api/connections/{connection_id}/activities",
                query={"limit": str(limit)},
            )
        )
        return [self._expect_activity(value) for value in values]

    def create_activity(
        self,
        package_name: str,
        app_name: str,
        event_type: str,
        recorded_at: str,
    ) -> dict[str, Any]:
        event_key = sha256(
            "|".join((package_name, event_type, recorded_at)).encode("utf-8")
        ).hexdigest()
        result = self._request(
            "POST",
            "/api/activities",
            {
                "package_name": package_name,
                "app_name": app_name,
                "event_type": event_type,
                "recorded_at": recorded_at,
                "event_key": event_key,
            },
        )
        return self._expect_activity(result)

    def get_restricted_apps(self) -> list[dict[str, Any]]:
        values = self._expect_list(self._request("GET", "/api/restrictions/me"))
        for value in values:
            self._expect_object(
                value,
                {
                    "id": int,
                    "package_name": str,
                    "app_name": str,
                    "created_at": str,
                },
            )
        return values

    def update_restricted_apps(
        self, apps: list[dict[str, str]]
    ) -> list[dict[str, Any]]:
        values = self._expect_list(
            self._request("PUT", "/api/restrictions/me", {"apps": apps})
        )
        for value in values:
            self._expect_object(
                value,
                {
                    "id": int,
                    "package_name": str,
                    "app_name": str,
                    "created_at": str,
                },
            )
        return values

    def get_restriction_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        values = self._expect_list(
            self._request(
                "GET",
                "/api/restrictions/alerts/me",
                query={"limit": str(limit)},
            )
        )
        for value in values:
            self._expect_object(
                value,
                {
                    "id": int,
                    "package_name": str,
                    "app_name": str,
                    "recorded_at": str,
                },
            )
        return values

    def get_shared_restriction_alerts(
        self, connection_id: int, limit: int = 50
    ) -> list[dict[str, Any]]:
        values = self._expect_list(
            self._request(
                "GET",
                f"/api/connections/{connection_id}/restriction-alerts",
                query={"limit": str(limit)},
            )
        )
        for value in values:
            self._expect_object(
                value,
                {
                    "id": int,
                    "package_name": str,
                    "app_name": str,
                    "recorded_at": str,
                },
            )
        return values

    def create_restriction_alert(
        self,
        package_name: str,
        app_name: str,
        recorded_at: str,
        details: str,
    ) -> dict[str, Any]:
        result = self._request(
            "POST",
            "/api/restrictions/alerts",
            {
                "package_name": package_name,
                "app_name": app_name,
                "recorded_at": recorded_at,
                "details": details,
            },
        )
        return self._expect_object(
            result,
            {
                "id": int,
                "package_name": str,
                "app_name": str,
                "recorded_at": str,
            },
        )
