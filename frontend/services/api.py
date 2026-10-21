import json
import os
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


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
        if self._is_android() and not normalized.startswith("https://"):
            raise ValueError("Android API URLs must use HTTPS.")
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
        try:
            with urlopen(request, timeout=15) as response:
                if response.status == 204:
                    return None
                response_body = response.read()
                if not response_body:
                    return None
                try:
                    return json.loads(response_body)
                except json.JSONDecodeError as error:
                    raise ApiError("The API returned invalid JSON.") from error
        except HTTPError as error:
            if error.code == 401 and self.token:
                self.logout()
                if self.on_unauthorized:
                    self.on_unauthorized()
            try:
                details = json.loads(error.read())
                message = details.get("detail", "The server rejected the request.")
            except (json.JSONDecodeError, AttributeError):
                message = "The server rejected the request."
            raise ApiError(f"{error.code}: {message}", status_code=error.code) from error
        except URLError as error:
            raise ApiError(
                "Could not reach the API. Check the API URL and network connection."
            ) from error
        except TimeoutError as error:
            raise ApiError("The API request timed out.") from error

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
