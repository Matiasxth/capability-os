"""Supervisor Daemon — orchestrates all monitoring modules.

Starts health monitor, error interceptor, and provides unified status.
Communicates with the user via event bus notifications.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .claude_bridge import ClaudeBridge
from .error_interceptor import ErrorInterceptor
from .health_monitor import HealthMonitor


class SupervisorDaemon:
    """Main supervisor — coordinates all monitoring and auto-healing."""

    def __init__(
        self,
        project_root: Path,
        skill_creator: Any = None,
        max_claude_per_hour: int = 10,
        health_interval_s: int = 60,
    ) -> None:
        self._root = project_root
        self._claude = ClaudeBridge(project_root, max_per_hour=max_claude_per_hour)
        self._health = HealthMonitor(interval_s=health_interval_s)
        self._error_interceptor = ErrorInterceptor(
            claude_bridge=self._claude,
            skill_creator=skill_creator,
        )
        self._running = False
        self._started_at: str | None = None

        # Wire health failures to supervisor
        self._health.on_failure(self._on_health_failure)

    def start(self, event_bus: Any) -> None:
        """Start all monitoring modules."""
        if self._running:
            return
        self._running = True
        self._started_at = _now()

        # Subscribe error interceptor to event bus
        self._error_interceptor.subscribe(event_bus)

        # Start health monitor
        self._health.start()

        print(f"[SUPERVISOR] Started (claude={'available' if self._claude.available else 'not found'})", flush=True)

    def stop(self) -> None:
        self._running = False
        self._health.stop()

    def get_status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "started_at": self._started_at,
            "health": {
                "status": self._health.status,
                "checks": self._health.last_results,
                "running": self._health.running,
            },
            "claude": {
                "available": self._claude.available,
                "invocations": self._claude.invocation_count,
            },
            "errors": {
                "recent": self._error_interceptor.recent_log[-10:],
                "summary": self._error_interceptor.error_summary,
            },
        }

    def get_full_log(self) -> list[dict[str, Any]]:
        """Combined log from all modules."""
        combined = []
        combined.extend({"source": "error", **e} for e in self._error_interceptor.recent_log)
        combined.extend({"source": "claude", **c} for c in self._claude.recent_log)
        combined.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return combined[:50]

    def invoke_claude(self, prompt: str) -> str:
        """Manual Claude invocation from the dashboard."""
        return self._claude.analyze(prompt)

    @property
    def claude_bridge(self) -> ClaudeBridge:
        return self._claude

    @property
    def health_monitor(self) -> HealthMonitor:
        return self._health

    @property
    def error_interceptor(self) -> ErrorInterceptor:
        return self._error_interceptor

    def _on_health_failure(self, failed_checks: list[dict[str, Any]]) -> None:
        """React to health check failures."""
        names = [c["check"] for c in failed_checks]
        print(f"[SUPERVISOR] Health failure: {', '.join(names)}", flush=True)

        # Emit alert
        try:
            from system.core.ui_bridge.event_bus import event_bus
            event_bus.emit("supervisor_alert", {
                "severity": "warning",
                "source": "health_monitor",
                "failed_checks": names,
            })
        except Exception:
            pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
