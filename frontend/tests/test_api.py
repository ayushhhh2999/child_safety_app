import json
import os
import unittest
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError

from services.api import ApiClient, ApiError


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
