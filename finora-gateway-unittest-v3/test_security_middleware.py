"""Unit tests for the local Finora Flask gateway middleware.

Run from the directory that contains app.py:
    python -m unittest -v test_security_middleware

All Redis and backend calls are mocked; these tests do not contact the real
Redis server, C# API, or MySQL database.
"""
from types import SimpleNamespace
import os
import unittest
from unittest.mock import Mock, patch

# Test the documented local-gateway configuration: no trusted reverse proxy.
os.environ["TRUSTED_X_FOR_COUNT"] = "0"
os.environ["TRUSTED_X_PROTO_COUNT"] = "0"

import app as gateway

ALLOWED_ORIGIN = "http://localhost:8080"
BAD_ORIGIN = "https://evil.example"
API_PATH = "/api/chuyen-khoan"


class SecurityMiddlewareTests(unittest.TestCase):
    def setUp(self):
        self.client = gateway.app.test_client()
        self.redis_sismember = patch.object(
            gateway.redis_client, "sismember", return_value=False
        )
        self.mock_sismember = self.redis_sismember.start()
        self.addCleanup(self.redis_sismember.stop)

        self.rate_limit = patch.object(
            gateway, "apply_rate_limit", return_value=None
        )
        self.mock_rate_limit = self.rate_limit.start()
        self.addCleanup(self.rate_limit.stop)

        self.backend = patch.object(
            gateway.requests,
            "request",
            return_value=SimpleNamespace(
                content=b"", status_code=401,
                headers={"WWW-Authenticate": "Bearer"}
            ),
        )
        self.mock_backend = self.backend.start()
        self.addCleanup(self.backend.stop)

    def test_allowed_origin_preflight_returns_cors_headers(self):
        response = self.client.options(
            API_PATH,
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers":
                    "content-type,authorization,idempotency-key",
            },
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            response.headers.get("Access-Control-Allow-Origin"),
            ALLOWED_ORIGIN,
        )
        allowed_headers = response.headers.get(
            "Access-Control-Allow-Headers", ""
        ).lower()
        for header in ("content-type", "authorization", "idempotency-key"):
            self.assertIn(header, allowed_headers)
        self.mock_backend.assert_not_called()

    def test_disallowed_origin_preflight_has_no_cors_permission(self):
        response = self.client.options(
            API_PATH,
            headers={
                "Origin": BAD_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        self.assertEqual(response.status_code, 204)
        self.assertNotEqual(
            response.headers.get("Access-Control-Allow-Origin"), BAD_ORIGIN
        )
        self.assertNotIn("Access-Control-Allow-Headers", response.headers)
        self.mock_backend.assert_not_called()

    def test_disallowed_custom_header_is_not_allowed_by_preflight(self):
        response = self.client.options(
            API_PATH,
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "x-finora-test",
            },
        )
        self.assertEqual(response.status_code, 204)
        self.assertNotIn("Access-Control-Allow-Headers", response.headers)

    def test_bad_origin_is_rejected_before_backend(self):
        response = self.client.post(
            API_PATH,
            headers={"Origin": BAD_ORIGIN, "Content-Type": "application/json"},
            json={},
        )
        self.assertEqual(response.status_code, 403)
        # Rate limiting should execute before Origin validation.
        self.mock_sismember.assert_called_once()
        self.mock_rate_limit.assert_called_once()
        self.mock_backend.assert_not_called()

    def test_bad_referer_is_rejected_before_backend(self):
        response = self.client.post(
            API_PATH,
            headers={
                "Referer": "https://evil.example/page",
                "Content-Type": "application/json",
            },
            json={},
        )
        self.assertEqual(response.status_code, 403)
        # Rate limiting should execute before Referer validation.
        self.mock_sismember.assert_called_once()
        self.mock_rate_limit.assert_called_once()
        self.mock_backend.assert_not_called()

    def test_good_origin_does_not_override_bad_referer(self):
        response = self.client.post(
            API_PATH,
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Referer": "https://evil.example/page",
                "Content-Type": "application/json",
            },
            json={},
        )
        self.assertEqual(response.status_code, 403)
        self.mock_backend.assert_not_called()

    def test_malformed_origin_values_are_rejected(self):
        for origin in ("null", "file://evil.example", "http://localhost:8080/path"):
            with self.subTest(origin=origin):
                response = self.client.post(
                    API_PATH,
                    headers={"Origin": origin, "Content-Type": "application/json"},
                    json={},
                )
                self.assertEqual(response.status_code, 403)
        self.mock_backend.assert_not_called()

    def test_malformed_referer_values_are_rejected(self):
        for referer in ("not-a-url", "file://evil.example/page"):
            with self.subTest(referer=referer):
                response = self.client.post(
                    API_PATH,
                    headers={"Referer": referer, "Content-Type": "application/json"},
                    json={},
                )
                self.assertEqual(response.status_code, 403)
        self.mock_backend.assert_not_called()

    def test_good_origin_and_referer_continue_to_backend_auth(self):
        response = self.client.post(
            API_PATH,
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Referer": f"{ALLOWED_ORIGIN}/finora",
                "Content-Type": "application/json",
            },
            json={},
        )
        self.assertEqual(response.status_code, 401)
        self.mock_backend.assert_called_once()

    def test_missing_origin_and_referer_continue_to_backend_auth(self):
        response = self.client.post(
            API_PATH,
            headers={"Content-Type": "application/json"},
            json={},
        )
        self.assertEqual(response.status_code, 401)
        self.mock_backend.assert_called_once()

    def test_rate_limit_precedes_origin_validation(self):
        gateway_response = gateway.app.response_class(
            '{"error":"Too many requests."}',
            status=429,
            mimetype="application/json",
        )
        self.mock_rate_limit.return_value = gateway_response

        response = self.client.post(
            API_PATH,
            headers={"Origin": BAD_ORIGIN, "Content-Type": "application/json"},
            json={},
        )

        # 429 proves Rate Limiting ran before the bad Origin could return 403.
        self.assertEqual(response.status_code, 429)
        self.mock_sismember.assert_called_once()
        self.mock_rate_limit.assert_called_once()
        self.mock_backend.assert_not_called()

    def test_rate_limit_precedes_referer_validation(self):
        gateway_response = gateway.app.response_class(
            '{"error":"Too many requests."}',
            status=429,
            mimetype="application/json",
        )
        self.mock_rate_limit.return_value = gateway_response

        response = self.client.post(
            API_PATH,
            headers={
                "Referer": "https://evil.example/page",
                "Content-Type": "application/json",
            },
            json={},
        )

        # 429 proves Rate Limiting ran before the bad Referer could return 403.
        self.assertEqual(response.status_code, 429)
        self.mock_sismember.assert_called_once()
        self.mock_rate_limit.assert_called_once()
        self.mock_backend.assert_not_called()

    def test_client_supplied_x_forwarded_for_is_overwritten(self):
        spoofed_ip = "203.0.113.77"
        response = self.client.get(
            API_PATH,
            headers={"X-Forwarded-For": spoofed_ip},
        )

        self.assertEqual(response.status_code, 401)
        forwarded_headers = self.mock_backend.call_args.kwargs["headers"]
        self.assertEqual(forwarded_headers.get("X-Forwarded-For"), "127.0.0.1")
        self.assertNotEqual(
            forwarded_headers.get("X-Forwarded-For"), spoofed_ip
        )

    def test_client_supplied_x_forwarded_proto_is_overwritten(self):
        response = self.client.get(
            API_PATH,
            headers={"X-Forwarded-Proto": "https"},
        )

        self.assertEqual(response.status_code, 401)
        forwarded_headers = self.mock_backend.call_args.kwargs["headers"]
        self.assertEqual(forwarded_headers.get("X-Forwarded-Proto"), "http")
        self.assertNotIn("Strict-Transport-Security", response.headers)

    def test_blacklisted_ip_is_rejected(self):
        self.mock_sismember.return_value = True
        response = self.client.get(API_PATH)
        self.assertEqual(response.status_code, 403)
        self.mock_backend.assert_not_called()

    def test_rate_limited_request_returns_429(self):
        gateway_response = gateway.app.response_class(
            '{"error":"Too many requests."}',
            status=429,
            mimetype="application/json",
        )
        gateway_response.headers["Retry-After"] = "7"
        self.mock_rate_limit.return_value = gateway_response

        response = self.client.options(
            API_PATH,
            headers={"Origin": ALLOWED_ORIGIN},
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers.get("Retry-After"), "7")
        self.mock_backend.assert_not_called()

    def test_redis_error_fails_closed_with_503(self):
        self.mock_sismember.side_effect = gateway.redis.RedisError("test failure")
        response = self.client.get(API_PATH)
        self.assertEqual(response.status_code, 503)
        self.mock_backend.assert_not_called()

    def test_security_headers_are_added_to_rejection_responses(self):
        response = self.client.post(
            API_PATH,
            headers={"Origin": BAD_ORIGIN, "Content-Type": "application/json"},
            json={},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertIn("frame-ancestors 'none'", response.headers.get("Content-Security-Policy", ""))
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")

    def test_healthcheck_reports_redis_status(self):
        with patch.object(gateway.redis_client, "ping", return_value=True):
            response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok", "redis": "connected"})
        self.mock_backend.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
