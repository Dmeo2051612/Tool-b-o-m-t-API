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
# Configure multiple allowed origins so the suite can verify Origin variation
# and the corresponding Vary response header behavior.
os.environ["ALLOWED_ORIGINS"] = (
    "http://localhost:8080,http://127.0.0.1:8080"
)

import app as gateway

ALLOWED_ORIGIN = "http://localhost:8080"
SECOND_ALLOWED_ORIGIN = "http://127.0.0.1:8080"
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

    def test_second_allowed_origin_is_echoed_exactly(self):
        response = self.client.options(
            API_PATH,
            headers={
                "Origin": SECOND_ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,authorization",
            },
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            response.headers.get("Access-Control-Allow-Origin"),
            SECOND_ALLOWED_ORIGIN,
        )

    def test_cors_varies_origin_for_multiple_allowed_origins(self):
        for origin in (ALLOWED_ORIGIN, SECOND_ALLOWED_ORIGIN):
            with self.subTest(origin=origin):
                response = self.client.get(API_PATH, headers={"Origin": origin})
                self.assertEqual(response.status_code, 401)
                self.assertEqual(
                    response.headers.get("Access-Control-Allow-Origin"),
                    origin,
                )
                vary_values = {
                    part.strip().lower()
                    for part in response.headers.get("Vary", "").split(",")
                    if part.strip()
                }
                self.assertIn("origin", vary_values)

    def test_disallowed_origin_never_receives_allow_origin_header(self):
        response = self.client.get(API_PATH, headers={"Origin": BAD_ORIGIN})
        self.assertEqual(response.status_code, 401)
        self.assertNotEqual(
            response.headers.get("Access-Control-Allow-Origin"), BAD_ORIGIN
        )

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


    def test_invalid_client_ip_is_rejected_before_redis(self):
        response = self.client.get(
            API_PATH,
            environ_overrides={"REMOTE_ADDR": "not-an-ip"},
        )
        self.assertEqual(response.status_code, 400)
        self.mock_sismember.assert_not_called()
        self.mock_rate_limit.assert_not_called()
        self.mock_backend.assert_not_called()

    def test_backend_timeout_returns_504(self):
        self.mock_backend.side_effect = gateway.requests.Timeout("test timeout")
        response = self.client.get(API_PATH)
        self.assertEqual(response.status_code, 504)
        self.assertEqual(
            response.get_json(),
            {"error": "Backend không phản hồi kịp thời."},
        )

    def test_backend_connection_error_returns_502(self):
        self.mock_backend.side_effect = gateway.requests.ConnectionError(
            "test connection failure"
        )
        response = self.client.get(API_PATH)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.get_json(),
            {"error": "Không thể kết nối tới backend."},
        )

    def test_client_hop_by_hop_and_forwarded_headers_are_not_forwarded(self):
        response = self.client.get(
            API_PATH,
            headers={
                "Connection": "X-Internal-Token",
                "X-Internal-Token": "do-not-forward",
                "X-Forwarded-Host": "evil.example",
                "X-Forwarded-Port": "9999",
                "X-Forwarded-For": "203.0.113.77",
            },
        )
        self.assertEqual(response.status_code, 401)
        forwarded = self.mock_backend.call_args.kwargs["headers"]
        lowered = {name.lower(): value for name, value in forwarded.items()}
        self.assertNotIn("x-internal-token", lowered)
        self.assertNotIn("x-forwarded-host", lowered)
        self.assertNotIn("x-forwarded-port", lowered)
        self.assertEqual(lowered.get("x-forwarded-for"), "127.0.0.1")

    def test_hop_by_hop_and_cors_headers_from_backend_are_filtered(self):
        self.mock_backend.return_value = SimpleNamespace(
            content=b"ok",
            status_code=200,
            headers={
                "Connection": "keep-alive",
                "Transfer-Encoding": "chunked",
                "Content-Encoding": "gzip",
                "Access-Control-Allow-Origin": BAD_ORIGIN,
                "X-Upstream-Test": "preserved",
            },
        )
        response = self.client.get(
            API_PATH, headers={"Origin": ALLOWED_ORIGIN}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Upstream-Test"), "preserved")
        self.assertNotIn("Connection", response.headers)
        self.assertNotIn("Transfer-Encoding", response.headers)
        self.assertNotIn("Content-Encoding", response.headers)
        # The untrusted upstream CORS header must be filtered. Flask-CORS may
        # then add the configured allowlisted origin to the final response.
        self.assertEqual(
            response.headers.get("Access-Control-Allow-Origin"), ALLOWED_ORIGIN
        )
        self.assertNotEqual(
            response.headers.get("Access-Control-Allow-Origin"), BAD_ORIGIN
        )

    def test_healthcheck_returns_503_when_redis_ping_fails(self):
        with patch.object(
            gateway.redis_client,
            "ping",
            side_effect=gateway.redis.RedisError("test ping failure"),
        ):
            response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json(),
            {"status": "degraded", "redis": "unavailable"},
        )
        self.mock_backend.assert_not_called()


    def test_normalize_origin_lowercases_scheme_and_host(self):
        self.assertEqual(
            gateway.normalize_origin("HTTP://LOCALHOST:8080"),
            "http://localhost:8080",
        )
        self.assertEqual(
            gateway.normalize_origin("HtTpS://Example.COM"),
            "https://example.com",
        )

    def test_normalize_origin_removes_default_ports(self):
        self.assertEqual(
            gateway.normalize_origin("http://localhost:80"),
            "http://localhost",
        )
        self.assertEqual(
            gateway.normalize_origin("https://example.com:443"),
            "https://example.com",
        )

    def test_normalize_origin_rejects_userinfo_query_fragment_and_invalid_port(self):
        invalid_values = (
            "http://user:pass@localhost:8080",
            "http://localhost:8080?x=1",
            "http://localhost:8080#fragment",
            "http://localhost:not-a-port",
        )
        for value in invalid_values:
            with self.subTest(value=value):
                self.assertIsNone(gateway.normalize_origin(value))



    def test_normalize_origin_trims_surrounding_whitespace(self):
        self.assertEqual(
            gateway.normalize_origin("  HTTP://LOCALHOST:8080  "),
            "http://localhost:8080",
        )

    def test_normalize_origin_handles_ipv6_literals(self):
        self.assertEqual(
            gateway.normalize_origin("http://[::1]:80"),
            "http://[::1]",
        )
        self.assertEqual(
            gateway.normalize_origin("https://[2001:DB8::1]:8443"),
            "https://[2001:db8::1]:8443",
        )

    def test_normalize_origin_rejects_malformed_ipv6_and_out_of_range_port(self):
        invalid_values = (
            "http://[:::1]:8080",
            "http://localhost:65536",
            "https://[2001:db8::1]:99999",
        )
        for value in invalid_values:
            with self.subTest(value=value):
                self.assertIsNone(gateway.normalize_origin(value))


    def test_get_with_bad_referer_continues_to_backend_auth(self):
        response = self.client.get(
            API_PATH,
            headers={"Referer": "https://evil.example/page"},
        )
        # Origin/Referer enforcement is for state-changing methods only.
        # Backend authentication still protects a read request.
        self.assertEqual(response.status_code, 401)
        self.mock_backend.assert_called_once()

    def test_empty_origin_is_rejected(self):
        response = self.client.post(
            API_PATH,
            headers={"Origin": "", "Content-Type": "application/json"},
            json={},
        )
        self.assertEqual(response.status_code, 403)
        self.mock_backend.assert_not_called()

    def test_empty_referer_is_rejected(self):
        response = self.client.post(
            API_PATH,
            headers={"Referer": "", "Content-Type": "application/json"},
            json={},
        )
        self.assertEqual(response.status_code, 403)
        self.mock_backend.assert_not_called()

    def test_hsts_is_added_for_https_request(self):
        response = self.client.get(API_PATH, base_url="https://localhost")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.headers.get("Strict-Transport-Security"),
            "max-age=31536000",
        )
        forwarded_headers = self.mock_backend.call_args.kwargs["headers"]
        self.assertEqual(
            forwarded_headers.get("X-Forwarded-Proto"), "https"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
