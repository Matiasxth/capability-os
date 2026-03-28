"""Detects unhealthy capabilities and suggests improvements.

Reads recent execution traces from MetricsCollector, identifies capabilities
with high error rates, and generates typed improvement suggestions:

  - ``retry_policy``  — when failures concentrate on a specific step
  - ``fallback``      — when the capability fails across all attempts
  - ``increase_timeout`` — when failures are timeout-related

Spec section 14 rule: suggestions are **read-only proposals**.  Nothing is
modified or installed without explicit user approval.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

from system.core.metrics import MetricsCollector


_ERROR_RATE_THRESHOLD = 0.20  # 20 %
_WINDOW_SIZE = 10             # last N executions per capability
_TIMEOUT_ERROR_CODES = frozenset({
    "browser_worker_timeout",
    "navigation_failed",
    "selector_not_found",
    "wait_failed",
})


class PerformanceMonitor:
    """Analyzes recent traces and produces improvement suggestions."""

    def __init__(
        self,
        metrics_collector: MetricsCollector,
        error_rate_threshold: float = _ERROR_RATE_THRESHOLD,
        window_size: int = _WINDOW_SIZE,
    ):
        self._metrics = metrics_collector
        self._error_rate_threshold = max(0.01, float(error_rate_threshold))
        self._window_size = max(1, int(window_size))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_improvement_suggestions(self) -> list[dict[str, Any]]:
        """Return a list of improvement suggestions for unhealthy capabilities."""
        traces_by_cap = self._recent_traces_by_capability()
        suggestions: list[dict[str, Any]] = []

        for capability_id, traces in sorted(traces_by_cap.items()):
            total = len(traces)
            errors = [t for t in traces if t.get("status") == "error"]
            if total == 0:
                continue
            error_rate = len(errors) / total
            if error_rate < self._error_rate_threshold:
                continue

            suggestion = self._diagnose(capability_id, errors, error_rate, total)
            suggestions.append(suggestion)

        return suggestions

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _recent_traces_by_capability(self) -> dict[str, list[dict[str, Any]]]:
        """Load the most recent traces and group by capability_id."""
        # Fetch enough traces to cover multiple capabilities
        trace_ids = self._metrics.list_traces(limit=self._window_size * 20)
        by_cap: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for trace_id in trace_ids:
            trace = self._metrics.get_trace(trace_id)
            if trace is None:
                continue
            cap_id = trace.get("capability_id", "unknown")
            if len(by_cap[cap_id]) < self._window_size:
                by_cap[cap_id].append(trace)

        return dict(by_cap)

    def _diagnose(
        self,
        capability_id: str,
        error_traces: list[dict[str, Any]],
        error_rate: float,
        total: int,
    ) -> dict[str, Any]:
        """Classify the failure pattern and produce a typed suggestion."""
        failed_steps = self._extract_failed_steps(error_traces)
        error_codes = self._extract_error_codes(error_traces)

        suggestion_type, reason = self._classify_failure(
            failed_steps, error_codes, error_rate,
        )

        return {
            "capability_id": capability_id,
            "suggestion_type": suggestion_type,
            "reason": reason,
            "error_rate": round(error_rate * 100, 1),
            "total_in_window": total,
            "errors_in_window": len(error_traces),
            "failed_steps": dict(failed_steps),
            "error_codes": dict(error_codes),
        }

    @staticmethod
    def _classify_failure(
        failed_steps: dict[str, int],
        error_codes: dict[str, int],
        error_rate: float,
    ) -> tuple[str, str]:
        """Return (suggestion_type, human_reason)."""
        # Check if timeouts dominate
        timeout_count = sum(
            error_codes.get(code, 0) for code in _TIMEOUT_ERROR_CODES
        )
        total_errors = sum(error_codes.values()) or 1
        if timeout_count / total_errors >= 0.5:
            return (
                "increase_timeout",
                f"Timeout-related errors account for {timeout_count}/{total_errors} failures.",
            )

        # Check if failures concentrate on a single step
        if failed_steps:
            top_step, top_count = max(failed_steps.items(), key=lambda x: x[1])
            if top_count / total_errors >= 0.6:
                return (
                    "retry_policy",
                    f"Step '{top_step}' accounts for {top_count}/{total_errors} failures. "
                    "A retry_policy on this step may recover from transient issues.",
                )

        # General failure → fallback
        return (
            "fallback",
            f"Error rate is {round(error_rate * 100, 1)}% across multiple steps. "
            "Consider adding a fallback strategy.",
        )

    @staticmethod
    def _extract_failed_steps(traces: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for trace in traces:
            step = trace.get("failed_step")
            if isinstance(step, str) and step:
                counts[step] += 1
        return dict(counts)

    @staticmethod
    def _extract_error_codes(traces: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for trace in traces:
            code = trace.get("error_code")
            if isinstance(code, str) and code:
                counts[code] += 1
        return dict(counts)
