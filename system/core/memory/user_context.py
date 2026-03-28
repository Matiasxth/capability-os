"""High-level user context layer over MemoryManager.

Learns from execution history to build a profile of the user's
preferences and patterns.  Exposes a unified ``get_context()`` dict
that the CapabilityEngine can inject as ``{{state.user_context.*}}``.

Rule 5: all learning is wrapped in try/except — a failure in context
building never blocks an execution.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from system.core.memory.memory_manager import MemoryManager
from system.core.metrics import MetricsCollector


# Memory keys
_KEY_LANGUAGE = "user:preferred_language"
_KEY_FREQUENT_CAPS = "user:frequent_capabilities"
_KEY_LAST_WORKSPACE = "user:last_workspace_path"
_KEY_CUSTOM_PREFS = "user:custom_preferences"
_KEY_CAP_USAGE_PREFIX = "usage:capability:"

_FREQUENT_TOP_N = 5
_LEARN_THRESHOLD = 5  # minimum uses before remembering a pattern


class UserContext:
    """Builds and queries a user profile from memory + metrics."""

    def __init__(
        self,
        memory: MemoryManager,
        metrics: MetricsCollector | None = None,
    ):
        self._memory = memory
        self._metrics = metrics

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_context(self) -> dict[str, Any]:
        """Return the full user context dict.

        Safe to call at any time — returns ``{}`` on any internal error.
        """
        try:
            return {
                "preferred_language": self._memory.recall(_KEY_LANGUAGE),
                "frequent_capabilities": self._memory.recall(_KEY_FREQUENT_CAPS) or [],
                "last_workspace_path": self._memory.recall(_KEY_LAST_WORKSPACE),
                "custom_preferences": self._memory.recall(_KEY_CUSTOM_PREFS) or {},
            }
        except Exception:
            return {}

    def get_preference(self, key: str) -> Any | None:
        """Read a single custom preference."""
        prefs = self._memory.recall(_KEY_CUSTOM_PREFS)
        if isinstance(prefs, dict):
            return prefs.get(key)
        return None

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def set_preference(self, key: str, value: Any) -> None:
        """Store a user-defined preference."""
        prefs = self._memory.recall(_KEY_CUSTOM_PREFS)
        if not isinstance(prefs, dict):
            prefs = {}
        prefs[key] = value
        self._memory.remember(_KEY_CUSTOM_PREFS, prefs, memory_type="user_preference")

    def set_language(self, lang: str) -> None:
        self._memory.remember(_KEY_LANGUAGE, lang, memory_type="user_preference")

    def set_workspace_path(self, path: str) -> None:
        self._memory.remember(_KEY_LAST_WORKSPACE, path, memory_type="user_preference")

    # ------------------------------------------------------------------
    # Learning (called after executions)
    # ------------------------------------------------------------------

    def learn_from_execution(self, runtime_model: dict[str, Any]) -> None:
        """Extract patterns from a completed execution and update memory.

        Called by the ObservationLogger or API layer after each execution.
        Must never raise.
        """
        try:
            self._learn_capability_usage(runtime_model)
            self._learn_language_hint(runtime_model)
        except Exception:
            pass  # Rule 5

    def refresh_frequent_capabilities(self) -> list[str]:
        """Recompute the top-N most-used capabilities from memory.

        Returns the list of capability_ids.
        """
        try:
            usage_memories = self._memory.recall_all(memory_type="execution_pattern")
            counts: Counter[str] = Counter()
            for rec in usage_memories:
                key = rec.get("key", "")
                if key.startswith(_KEY_CAP_USAGE_PREFIX):
                    cap_id = key[len(_KEY_CAP_USAGE_PREFIX):]
                    count = rec.get("value", 0)
                    if isinstance(count, (int, float)) and count > 0:
                        counts[cap_id] = int(count)

            top = [cap_id for cap_id, _ in counts.most_common(_FREQUENT_TOP_N)]
            self._memory.remember(_KEY_FREQUENT_CAPS, top, memory_type="user_preference")
            return top
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Internal learning helpers
    # ------------------------------------------------------------------

    def _learn_capability_usage(self, runtime_model: dict[str, Any]) -> None:
        cap_id = runtime_model.get("capability_id")
        if not isinstance(cap_id, str) or not cap_id:
            return
        key = f"{_KEY_CAP_USAGE_PREFIX}{cap_id}"
        current = self._memory.recall(key)
        count = (current if isinstance(current, int) else 0) + 1
        self._memory.remember(key, count, memory_type="execution_pattern", capability_id=cap_id)

    def _learn_language_hint(self, runtime_model: dict[str, Any]) -> None:
        """Detect language from execution state or inputs (best-effort)."""
        state = runtime_model.get("state", {})
        if not isinstance(state, dict):
            return
        # Check for explicit locale/language fields in state
        for field in ("language", "locale", "lang"):
            val = state.get(field)
            if isinstance(val, str) and len(val) >= 2:
                self._memory.remember(_KEY_LANGUAGE, val[:5], memory_type="user_preference")
                return
