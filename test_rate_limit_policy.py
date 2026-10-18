import unittest
from unittest.mock import patch

import app as gateway


class FakeRedis:
    def sismember(self, _key, _member):
        return False


class RateLimitPolicyTests(unittest.TestCase):
    def setUp(self):
        self.counts = {}
        self.client = gateway.app.test_client()
        self.redis_patcher = patch.object(gateway, "redis_client", FakeRedis())
        self.script_patcher = patch.object(
            gateway,
            "RATE_LIMIT_SCRIPT",
            side_effect=self.fake_rate_limit_script,
        )
        self.forward_patcher = patch.object(
            gateway,
            "forward_to_backend",
            side_effect=lambda: gateway.jsonify({"forwarded": True}),
        )
        self.config_patcher = patch.multiple(
            gateway,
            MAX_REQUESTS=60,
            TIME_WINDOW=10,
            AUTH_MAX_REQUESTS=5,
            AUTH_TIME_WINDOW=60,
        )
        self.redis_patcher.start()
        self.script_patcher.start()
        self.forward_patcher.start()
        self.config_patcher.start()
        self.addCleanup(self.config_patcher.stop)
        self.addCleanup(self.forward_patcher.stop)
        self.addCleanup(self.script_patcher.stop)
        self.addCleanup(self.redis_patcher.stop)

    def fake_rate_limit_script(self, keys, args):
        key = keys[0]
        self.counts[key] = self.counts.get(key, 0) + 1
        return [self.counts[key], int(args[0])]

    def test_normal_api_allows_more_than_five_requests(self):
        for _ in range(10):
            response = self.client.get("/api/data")
            self.assertEqual(response.status_code, 200)

    def test_login_has_five_requests_per_minute(self):
        for _ in range(5):
            response = self.client.post("/api/auth/login", json={})
            self.assertEqual(response.status_code, 200)

        response = self.client.post("/api/auth/login", json={})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers.get("Retry-After"), "60")
        self.assertEqual(response.get_json()["scope"], "auth-login")

    def test_login_and_register_have_separate_auth_buckets(self):
        for _ in range(5):
            self.assertEqual(
                self.client.post("/api/auth/login", json={}).status_code,
                200,
            )

        for _ in range(5):
            self.assertEqual(
                self.client.post("/api/auth/register", json={}).status_code,
                200,
            )

    def test_general_quota_is_shared_by_normal_api_endpoints(self):
        for _ in range(60):
            response = self.client.get("/api/data")
            self.assertEqual(response.status_code, 200)

        response = self.client.get("/api/data")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.get_json()["scope"], "ip")


if __name__ == "__main__":
    unittest.main()
