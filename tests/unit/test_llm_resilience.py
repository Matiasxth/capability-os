"""Tests for LLM cache and circuit breaker."""
import time
import unittest

from system.core.interpretation.llm_cache import LLMCache
from system.core.interpretation.circuit_breaker import CircuitBreaker


class TestLLMCache(unittest.TestCase):

    def test_miss_then_hit(self):
        c = LLMCache()
        self.assertIsNone(c.get("sys", "user"))
        c.put("sys", "user", "response")
        self.assertEqual(c.get("sys", "user"), "response")

    def test_ttl_expiry(self):
        c = LLMCache(ttl_seconds=0.3)
        c.put("s", "u", "r")
        self.assertEqual(c.get("s", "u"), "r")
        time.sleep(0.5)
        self.assertIsNone(c.get("s", "u"))

    def test_max_entries_eviction(self):
        c = LLMCache(max_entries=2)
        c.put("s", "a", "1")
        c.put("s", "b", "2")
        c.put("s", "c", "3")  # evicts "a"
        self.assertIsNone(c.get("s", "a"))
        self.assertEqual(c.get("s", "b"), "2")
        self.assertEqual(c.get("s", "c"), "3")

    def test_stats(self):
        c = LLMCache()
        c.put("s", "u", "r")
        c.get("s", "u")  # hit
        c.get("s", "miss")  # miss
        s = c.stats
        self.assertEqual(s["hits"], 1)
        self.assertEqual(s["misses"], 1)
        self.assertEqual(s["size"], 1)

    def test_clear(self):
        c = LLMCache()
        c.put("s", "u", "r")
        c.clear()
        self.assertIsNone(c.get("s", "u"))


class TestCircuitBreaker(unittest.TestCase):

    def test_starts_closed(self):
        cb = CircuitBreaker()
        self.assertEqual(cb.state, "closed")
        self.assertTrue(cb.allow_request())

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_seconds=60)
        cb.record_failure()
        cb.record_failure()
        self.assertTrue(cb.allow_request())
        cb.record_failure()  # 3rd → open
        self.assertFalse(cb.allow_request())
        self.assertEqual(cb.state, "open")

    def test_success_resets_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()  # only 1 after reset
        self.assertTrue(cb.allow_request())

    def test_half_open_after_recovery(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_seconds=0.3)
        cb.record_failure()
        self.assertFalse(cb.allow_request())
        time.sleep(0.5)
        self.assertEqual(cb.state, "half_open")
        self.assertTrue(cb.allow_request())

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        self.assertFalse(cb.allow_request())
        cb.reset()
        self.assertTrue(cb.allow_request())


if __name__ == "__main__":
    unittest.main()
