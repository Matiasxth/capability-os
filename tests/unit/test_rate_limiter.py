"""Tests for the rate limiter."""
import unittest
from system.core.ui_bridge.rate_limiter import RateLimiter


class TestRateLimiter(unittest.TestCase):

    def test_allows_under_limit(self):
        rl = RateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            self.assertTrue(rl.allow("10.0.0.1"))

    def test_blocks_over_limit(self):
        rl = RateLimiter(max_requests=3, window_seconds=60)
        self.assertTrue(rl.allow("10.0.0.1"))
        self.assertTrue(rl.allow("10.0.0.1"))
        self.assertTrue(rl.allow("10.0.0.1"))
        self.assertFalse(rl.allow("10.0.0.1"))

    def test_exempt_ip_always_allowed(self):
        rl = RateLimiter(max_requests=1, window_seconds=60, exempt_ips={"127.0.0.1"})
        for _ in range(100):
            self.assertTrue(rl.allow("127.0.0.1"))

    def test_localhost_exempt_by_default(self):
        rl = RateLimiter(max_requests=1, window_seconds=60)
        self.assertTrue(rl.allow("127.0.0.1"))
        self.assertTrue(rl.allow("127.0.0.1"))

    def test_different_ips_independent(self):
        rl = RateLimiter(max_requests=1, window_seconds=60)
        self.assertTrue(rl.allow("10.0.0.1"))
        self.assertFalse(rl.allow("10.0.0.1"))
        self.assertTrue(rl.allow("10.0.0.2"))  # different IP

    def test_cleanup(self):
        rl = RateLimiter(max_requests=5, window_seconds=0.01)
        rl.allow("10.0.0.1")
        import time; time.sleep(0.02)
        rl.cleanup()
        # Bucket should be empty now, allow again
        self.assertTrue(rl.allow("10.0.0.1"))


if __name__ == "__main__":
    unittest.main()
