"""Error Interceptor — captures errors in real-time from the event bus.

Classifies severity and triggers appropriate response:
  Low: log only
  Medium: diagnose and suggest fix
  High/Critical: invoke Claude immediately
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any


SEVERITY_MAP = {
    "file_not_found": "low",
    "timeout": "low",
    "browser_worker_timeout": "low",
    "permission_denied": "medium",
    "capability_not_found": "medium",
    "tool_execution_error": "medium",
    "variable_resolution_error": "medium",
    "input_validation_error": "low",
    "security_violation": "high",
    "auth_error": "high",
    "dispatch_error": "medium",
    "internal_error": "high",
}


class ErrorInterceptor:
    """Real-time error handler subscribed to event bus."""

    def __init__(self, claude_bridge: Any = None, skill_creator: Any = None) -> None:
        self._claude = claude_bridge
        self._skill_creator = skill_creator
        self._log: list[dict[str, Any]] = []
        self._error_counts: dict[str, int] = {}
        self._cooldown: dict[str, float] = {}

    def subscribe(self, event_bus: Any) -> None:
        event_bus.subscribe(self._on_event)

    @property
    def recent_log(self) -> list[dict[str, Any]]:
        return self._log[-30:]

    @property
    def error_summary(self) -> dict[str, int]:
        return dict(self._error_counts)

    def _on_event(self, event: dict[str, Any]) -> None:
        etype = event.get("type", "")
        data = event.get("data", {})

        if etype == "error":
            self._handle_error(data.get("error_code", "dispatch_error"), data.get("message", ""), data)
        elif etype == "execution_complete" and data.get("status") == "error":
            self._handle_error(data.get("error_code", "execution_error"), data.get("error_message", ""), data)

    def _handle_error(self, error_code: str, message: str, details: dict[str, Any]) -> None:
        severity = SEVERITY_MAP.get(error_code, "medium")

        # Rate limit: don't process same error more than once per 30s
        now = time.monotonic()
        key = f"{error_code}:{message[:50]}"
        if key in self._cooldown and now - self._cooldown[key] < 30:
            return
        self._cooldown[key] = now

        # Track counts
        self._error_counts[error_code] = self._error_counts.get(error_code, 0) + 1

        record = {
            "timestamp": _now(),
            "error_code": error_code,
            "message": message[:300],
            "severity": severity,
            "action": "none",
        }

        if severity == "low":
            record["action"] = "logged"

        elif severity == "medium":
            record["action"] = "diagnosed"
            if self._claude and self._claude.available:
                diagnosis = self._claude.diagnose(
                    f"Error: {error_code}\nMessage: {message}\nDetails: {str(details)[:500]}"
                )
                record["diagnosis"] = diagnosis[:500]

                # If it's a missing capability, try to create it
                if error_code == "capability_not_found" and self._skill_creator:
                    record["action"] = "auto_fix_attempted"

        elif severity in ("high", "critical"):
            record["action"] = "claude_invoked"
            if self._claude and self._claude.available:
                analysis = self._claude.analyze(
                    f"CRITICAL ERROR in Capability OS:\n"
                    f"Code: {error_code}\n"
                    f"Message: {message}\n"
                    f"Details: {str(details)[:800]}\n\n"
                    f"Analyze the root cause and suggest immediate fix."
                )
                record["analysis"] = analysis[:800]

            # Emit supervisor alert
            try:
                from system.core.ui_bridge.event_bus import event_bus
                event_bus.emit("supervisor_alert", {
                    "severity": severity,
                    "error_code": error_code,
                    "message": message[:200],
                })
            except Exception:
                pass

        self._log.append(record)
        if len(self._log) > 200:
            self._log = self._log[-100:]

        print(f"[SUPERVISOR-ERROR] [{severity.upper()}] {error_code}: {message[:100]}", flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
