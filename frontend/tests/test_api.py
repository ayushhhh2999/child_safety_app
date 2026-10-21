import json
import os
import socket
import ssl
import unittest
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError, URLError

from api_config import DEFAULT_API_BASE_URL
from services.api import ApiClient, ApiError, NETWORK_TIMEOUT_SECONDS


class ApiClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.url_patch = patch.dict(
            os.environ,
            {"API_BASE_URL": "http://127.0.0.1:8000"},
        )
        self.url_patch.start()
        self.client = ApiClient()

    def tearDown(self) -> None:
        self.client.close()
        self.url_patch.stop()

    def test_login_sends_credentials_then_uses_bearer_token_for_me(self) -> None:
        token_response = MagicMock()
        token_response.__enter__.return_value = token_response
        token_response.status = 200
        token_response.read.return_value = json.dumps(
            {"access_token": "test-token", "token_type": "bearer"}
        ).encode()
        profile_response = MagicMock()
        profile_response.__enter__.return_value = profile_response
        profile_response.status = 200
        profile_response.read.return_value = json.dumps(
            {"id": 4, "username": "alice", "email": "alice@example.com"}
        ).encode()

        with patch(
            "services.api.urlopen",
            side_effect=[token_response, profile_response],
        ) as mocked_urlopen:
            user = self.client.login("alice", "password")

        self.assertEqual(user["id"], 4)
        self.assertEqual(mocked_urlopen.call_count, 2)
        login_request = mocked_urlopen.call_args_list[0].args[0]
        profile_request = mocked_urlopen.call_args_list[1].args[0]
        self.assertEqual(login_request.full_url, "http://127.0.0.1:8000/api/auth/login")
        self.assertEqual(
            json.loads(login_request.data),
            {"username": "alice", "password": "password"},
        )
        self.assertEqual(
            profile_request.get_header("Authorization"),
            "Bearer test-token",
        )
        self.assertEqual(
            mocked_urlopen.call_args_list[0].kwargs["timeout"],
            NETWORK_TIMEOUT_SECONDS,
        )
        tls_context = mocked_urlopen.call_args_list[0].kwargs["context"]
        self.assertTrue(tls_context.check_hostname)
        self.assertEqual(tls_context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(tls_context.get_ca_certs())

    def test_android_uses_production_url_instead_of_environment_or_saved_config(self) -> None:
        with (
            patch.object(ApiClient, "_is_android", return_value=True),
            patch.dict(
                os.environ,
                {
                    "API_BASE_URL": "http://127.0.0.1:8000",
                    "MOBILE_TRACKER_API_URL": "https://old.example.test",
                },
            ),
        ):
            self.assertEqual(self.client._load_base_url(), DEFAULT_API_BASE_URL)

    def test_android_rejects_a_different_api_host(self) -> None:
        with patch.object(ApiClient, "_is_android", return_value=True):
            with self.assertRaisesRegex(ValueError, DEFAULT_API_BASE_URL):
                self.client.set_base_url("https://old.example.test")

    def test_signup_uses_backend_route_and_expected_payload(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 201
        response.read.return_value = (
            b'{"id":4,"username":"alice","email":"alice@example.com"}'
        )

        with patch("services.api.urlopen", return_value=response) as mocked_urlopen:
            user = self.client.signup(
                "alice",
                "alice@example.com",
                "a-long-test-password",
            )

        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8000/api/auth/signup")
        self.assertEqual(
            json.loads(request.data),
            {
                "username": "alice",
                "email": "alice@example.com",
                "password": "a-long-test-password",
            },
        )
        self.assertEqual(user["id"], 4)

    def test_dns_failure_is_reported_and_logged_without_request_secrets(self) -> None:
        failure = URLError(socket.gaierror("name lookup failed"))
        with (
            patch("services.api.urlopen", side_effect=failure),
            self.assertLogs("services.api", level="WARNING") as captured,
        ):
            with self.assertRaises(ApiError) as raised:
                self.client._request(
                    "POST",
                    "/api/auth/login",
                    {"username": "alice", "password": "private-password"},
                )

        self.assertIn("resolve the API server name", str(raised.exception))
        self.assertIn("gaierror", captured.output[0])
        self.assertNotIn("private-password", "\n".join(captured.output))

    def test_timeout_is_reported_as_a_timeout(self) -> None:
        failure = URLError(socket.timeout("read timed out"))
        with patch("services.api.urlopen", side_effect=failure):
            with self.assertRaises(ApiError) as raised:
                self.client._request("GET", "/health")

        self.assertIn("timed out", str(raised.exception))

    def test_invalid_json_is_reported_and_logged(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b"not-json"

        with (
            patch("services.api.urlopen", return_value=response),
            self.assertLogs("services.api", level="WARNING") as captured,
        ):
            with self.assertRaisesRegex(ApiError, "invalid JSON"):
                self.client._request("GET", "/health")

        self.assertIn("method=GET path=/health", captured.output[0])

    def test_http_error_logs_status_without_response_body_or_secrets(self) -> None:
        error_body = MagicMock()
        error_body.read.return_value = b'{"detail":"Invalid username or password"}'
        error = HTTPError(
            "https://example.test/api/auth/login",
            401,
            "Unauthorized",
            {},
            error_body,
        )
        with (
            patch("services.api.urlopen", side_effect=error),
            self.assertLogs("services.api", level="WARNING") as captured,
        ):
            with self.assertRaises(ApiError) as raised:
                self.client._request(
                    "POST",
                    "/api/auth/login",
                    {"username": "alice", "password": "private-password"},
                )

        self.assertEqual(raised.exception.status_code, 401)
        self.assertIn("status=401", captured.output[0])
        self.assertNotIn("private-password", "\n".join(captured.output))
        self.assertNotIn("Invalid username or password", "\n".join(captured.output))

    def test_failed_profile_request_clears_token(self) -> None:
        token_response = MagicMock()
        token_response.__enter__.return_value = token_response
        token_response.status = 200
        token_response.read.return_value = b'{"access_token":"test-token"}'
        error_response = MagicMock()
        error_response.read.return_value = b'{"detail":"Unauthorized"}'
        error = HTTPError(
            "http://127.0.0.1:8000/api/auth/me",
            401,
            "Unauthorized",
            {},
            error_response,
        )

        with patch("services.api.urlopen", side_effect=[token_response, error]):
            with self.assertRaises(ApiError):
                self.client.login("alice", "password")

        self.assertIsNone(self.client.token)

    def test_permission_patch_uses_json_and_authenticated_header(self) -> None:
        self.client.token = "test-token"
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = (
            b'{"share_location":true,"share_app_usage":false,'
            b'"share_restriction_alerts":false,"paused":false}'
        )

        with patch("services.api.urlopen", return_value=response) as mocked_urlopen:
            self.client.update_permissions(12, share_location=True)

        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "http://127.0.0.1:8000/api/connections/12/permissions",
        )
        self.assertEqual(json.loads(request.data), {"share_location": True})
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")

    def test_location_upload_and_history_use_authenticated_api(self) -> None:
        self.client.token = "test-token"
        create_response = MagicMock()
        create_response.__enter__.return_value = create_response
        create_response.status = 201
        create_response.read.return_value = (
            b'{"id":3,"latitude":37.4,"longitude":-122.0,'
            b'"accuracy_meters":8.0,"recorded_at":"2026-01-01T12:00:00+00:00"}'
        )
        history_response = MagicMock()
        history_response.__enter__.return_value = history_response
        history_response.status = 200
        history_response.read.return_value = (
            b'[{"id":3,"latitude":37.4,"longitude":-122.0,'
            b'"accuracy_meters":8.0,"recorded_at":"2026-01-01T12:00:00+00:00"}]'
        )

        with patch(
            "services.api.urlopen",
            side_effect=[create_response, history_response],
        ) as mocked_urlopen:
            created = self.client.create_location(
                37.4,
                -122.0,
                8.0,
                "2026-01-01T12:00:00+00:00",
            )
            history = self.client.get_locations(limit=25)

        self.assertEqual(created["id"], 3)
        self.assertEqual(len(history), 1)
        upload_request = mocked_urlopen.call_args_list[0].args[0]
        history_request = mocked_urlopen.call_args_list[1].args[0]
        self.assertEqual(upload_request.full_url, "http://127.0.0.1:8000/api/locations")
        self.assertEqual(
            json.loads(upload_request.data),
            {
                "latitude": 37.4,
                "longitude": -122.0,
                "accuracy_meters": 8.0,
                "recorded_at": "2026-01-01T12:00:00+00:00",
            },
        )
        self.assertEqual(
            history_request.full_url,
            "http://127.0.0.1:8000/api/locations/me?limit=25",
        )
        self.assertEqual(upload_request.get_header("Authorization"), "Bearer test-token")

    def test_activity_and_restriction_data_use_real_api_responses(self) -> None:
        events_response = MagicMock()
        events_response.__enter__.return_value = events_response
        events_response.status = 200
        events_response.read.return_value = (
            b'[{"id":1,"package_name":"org.example.app","app_name":"Example",'
            b'"event_type":"opened","recorded_at":"2026-01-01T12:00:00+00:00"}]'
        )
        restrictions_response = MagicMock()
        restrictions_response.__enter__.return_value = restrictions_response
        restrictions_response.status = 200
        restrictions_response.read.return_value = (
            b'[{"id":2,"package_name":"org.example.app","app_name":"Example",'
            b'"created_at":"2026-01-01T12:00:00+00:00"}]'
        )

        with patch(
            "services.api.urlopen",
            side_effect=[events_response, restrictions_response],
        ) as mocked_urlopen:
            events = self.client.get_activities(limit=20)
            restrictions = self.client.update_restricted_apps(
                [{"package_name": "org.example.app", "app_name": "Example"}]
            )

        self.assertEqual(events[0]["event_type"], "opened")
        self.assertEqual(restrictions[0]["package_name"], "org.example.app")
        self.assertEqual(
            mocked_urlopen.call_args_list[0].args[0].full_url,
            "http://127.0.0.1:8000/api/activities/me?limit=20",
        )
        request = mocked_urlopen.call_args_list[1].args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8000/api/restrictions/me")
        self.assertEqual(
            json.loads(request.data),
            {"apps": [{"package_name": "org.example.app", "app_name": "Example"}]},
        )

    def test_shared_feeds_and_restriction_alert_api(self) -> None:
        self.client.token = "test-token"
        location = (
            b'[{"id":1,"latitude":37.4,"longitude":-122.0,'
            b'"accuracy_meters":8.0,"recorded_at":"2026-01-01T12:00:00+00:00"}]'
        )
        activity = (
            b'[{"id":2,"package_name":"org.example.app","app_name":"Example",'
            b'"event_type":"opened","recorded_at":"2026-01-01T12:00:00+00:00"}]'
        )
        alert = (
            b'{"id":3,"package_name":"org.example.app","app_name":"Example",'
            b'"recorded_at":"2026-01-01T12:00:00+00:00"}'
        )
        shared_alert = (
            b'[{"id":4,"package_name":"org.example.app","app_name":"Example",'
            b'"recorded_at":"2026-01-01T12:00:00+00:00"}]'
        )
        responses = []
        for body in (location, activity, alert, shared_alert):
            response = MagicMock()
            response.__enter__.return_value = response
            response.status = 200
            response.read.return_value = body
            responses.append(response)

        with patch(
            "services.api.urlopen", side_effect=responses
        ) as mocked_urlopen:
            locations = self.client.get_shared_locations(12, limit=10)
            activities = self.client.get_shared_activities(12, limit=10)
            created_alert = self.client.create_restriction_alert(
                "org.example.app",
                "Example",
                "2026-01-01T12:00:00+00:00",
                "Blocked by owner rule",
            )
            alerts = self.client.get_shared_restriction_alerts(12, limit=10)

        self.assertEqual(locations[0]["id"], 1)
        self.assertEqual(activities[0]["id"], 2)
        self.assertEqual(created_alert["id"], 3)
        self.assertEqual(alerts[0]["id"], 4)
        self.assertEqual(
            [
                call.args[0].full_url
                for call in mocked_urlopen.call_args_list
            ],
            [
                "http://127.0.0.1:8000/api/connections/12/locations?limit=10",
                "http://127.0.0.1:8000/api/connections/12/activities?limit=10",
                "http://127.0.0.1:8000/api/restrictions/alerts",
                "http://127.0.0.1:8000/api/connections/12/restriction-alerts?limit=10",
            ],
        )
        alert_request = mocked_urlopen.call_args_list[2].args[0]
        self.assertEqual(
            json.loads(alert_request.data),
            {
                "package_name": "org.example.app",
                "app_name": "Example",
                "recorded_at": "2026-01-01T12:00:00+00:00",
                "details": "Blocked by owner rule",
            },
        )

    def test_signup_rejects_unexpected_server_response(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 201
        response.read.return_value = b'{"message":"ok"}'

        with patch("services.api.urlopen", return_value=response):
            with self.assertRaises(ApiError):
                self.client.signup("alice", "alice@example.com", "password")

    def test_api_url_requires_http_scheme(self) -> None:
        with self.assertRaises(ValueError):
            self.client.set_base_url("example.invalid")

    def test_changing_api_base_url_clears_existing_token(self) -> None:
        self.client.token = "old-host-token"
        self.client.set_base_url("https://api.example.test")
        self.assertIsNone(self.client.token)
        self.assertEqual(self.client.base_url, "https://api.example.test")

    def test_expired_token_clears_session_and_notifies_app(self) -> None:
        self.client.token = "expired-token"
        unauthorized_callback = Mock()
        self.client.on_unauthorized = unauthorized_callback
        error_body = MagicMock()
        error_body.read.return_value = b'{"detail":"Invalid or expired access token"}'
        error = HTTPError(
            "http://127.0.0.1:8000/api/auth/me",
            401,
            "Unauthorized",
            {},
            error_body,
        )

        with patch("services.api.urlopen", side_effect=error):
            with self.assertRaises(ApiError) as raised:
                self.client._request("GET", "/api/auth/me")

        self.assertEqual(raised.exception.status_code, 401)
        self.assertIsNone(self.client.token)
        unauthorized_callback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
