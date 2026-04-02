"""Shared pytest configuration — auto-skip tests that need unavailable infra."""
import os
import pytest

# Tests that spin up the full server or need external services
_INTEGRATION_MODULES = {
    "test_browser_hardening_backend",
    "test_a2a_client",
    "test_phase8_intent_api",
}


def pytest_collection_modifyitems(config, items):
    """Skip integration tests in CI — they need full server, Redis, or LLM."""
    in_ci = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"
    if not in_ci:
        return

    skip_ci = pytest.mark.skip(reason="Integration test — skipped in CI")
    for item in items:
        module = item.module.__name__ if item.module else ""
        if any(name in module for name in _INTEGRATION_MODULES):
            item.add_marker(skip_ci)
