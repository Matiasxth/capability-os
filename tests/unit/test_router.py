"""Tests for the HTTP router."""
import unittest
from system.core.ui_bridge.router import Router


def _dummy(**kw):
    return "ok"


class TestRouter(unittest.TestCase):

    def test_exact_match(self):
        r = Router()
        r.add("GET", "/health", _dummy)
        m = r.dispatch("GET", "/health")
        self.assertIsNotNone(m)
        self.assertEqual(m.handler, _dummy)
        self.assertEqual(m.params, {})

    def test_exact_match_trailing_slash(self):
        r = Router()
        r.add("GET", "/health", _dummy)
        m = r.dispatch("GET", "/health/")
        self.assertIsNotNone(m)

    def test_no_match(self):
        r = Router()
        r.add("GET", "/health", _dummy)
        self.assertIsNone(r.dispatch("GET", "/unknown"))
        self.assertIsNone(r.dispatch("POST", "/health"))

    def test_param_match(self):
        r = Router()
        r.add("GET", "/capabilities/{capability_id}", _dummy)
        m = r.dispatch("GET", "/capabilities/read_file")
        self.assertIsNotNone(m)
        self.assertEqual(m.params, {"capability_id": "read_file"})

    def test_multi_param(self):
        r = Router()
        r.add("GET", "/workspaces/{ws_id}/files/{file_id}", _dummy)
        m = r.dispatch("GET", "/workspaces/ws_abc/files/f_123")
        self.assertIsNotNone(m)
        self.assertEqual(m.params, {"ws_id": "ws_abc", "file_id": "f_123"})

    def test_method_matters(self):
        get_h = lambda **kw: "get"
        post_h = lambda **kw: "post"
        r = Router()
        r.add("GET", "/data", get_h)
        r.add("POST", "/data", post_h)
        self.assertEqual(r.dispatch("GET", "/data").handler, get_h)
        self.assertEqual(r.dispatch("POST", "/data").handler, post_h)

    def test_exact_takes_priority(self):
        exact_h = lambda **kw: "exact"
        param_h = lambda **kw: "param"
        r = Router()
        r.add("GET", "/caps/health", exact_h)
        r.add("GET", "/caps/{id}", param_h)
        m = r.dispatch("GET", "/caps/health")
        self.assertEqual(m.handler, exact_h)

    def test_route_count(self):
        r = Router()
        r.add("GET", "/a", _dummy)
        r.add("POST", "/b/{id}", _dummy)
        self.assertEqual(r.route_count, 2)

    def test_case_insensitive_method(self):
        r = Router()
        r.add("get", "/x", _dummy)
        m = r.dispatch("GET", "/x")
        self.assertIsNotNone(m)


if __name__ == "__main__":
    unittest.main()
