"""Audit Logger — records policy decisions, service access, and plugin actions.

Provides a queryable in-memory audit trail with optional persistence.
Integrated with the PolicyEngine for automatic decision logging.

Usage::

    from system.sdk.audit import AuditLogger

    logger = AuditLogger()
    logger.log("policy_decision", plugin_id="ext.plugin",
               permission="filesystem.write", allowed=False)

    recent = logger.query(plugin_id="ext.plugin", limit=10)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

try:
    from typing import NotRequired
except ImportError:
    from typing_extensions import NotRequired

from typing import TypedDict


class AuditEntry(TypedDict):
    """A single audit log entry."""
    timestamp: str
    event: str              # "policy_decision", "service_access", "plugin_action", "plugin_lifecycle"
    plugin_id: str
    user_role: str
    permission: str
    allowed: bool
    detail: str


class AuditLogger:
    """In-memory audit trail with query support."""

    def __init__(self, max_entries: int = 5000) -> None:
        self._entries: list[AuditEntry] = []
        self._max = max_entries

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def log(
        self,
        event: str,
        plugin_id: str = "",
        user_role: str = "",
        permission: str = "",
        allowed: bool = True,
        detail: str = "",
    ) -> None:
        """Record an audit entry."""
        entry = AuditEntry(
            timestamp=_now(),
            event=event,
            plugin_id=plugin_id,
            user_role=user_role,
            permission=permission,
            allowed=allowed,
            detail=detail[:500],
        )
        self._entries.append(entry)
        if len(self._entries) > self._max:
            self._entries = self._entries[-(self._max // 2):]

    def log_policy_decision(
        self,
        permission: str,
        plugin_id: str = "",
        user_role: str = "",
        allowed: bool = True,
        rule_id: str = "",
        reason: str = "",
    ) -> None:
        """Convenience method for policy decisions."""
        self.log(
            event="policy_decision",
            plugin_id=plugin_id,
            user_role=user_role,
            permission=permission,
            allowed=allowed,
            detail=f"rule={rule_id}: {reason}" if rule_id else reason,
        )

    def log_service_access(
        self,
        plugin_id: str,
        service_name: str,
        allowed: bool = True,
    ) -> None:
        """Log a service access attempt."""
        self.log(
            event="service_access",
            plugin_id=plugin_id,
            permission=f"service.{service_name}",
            allowed=allowed,
        )

    def log_plugin_lifecycle(
        self,
        plugin_id: str,
        action: str,
        detail: str = "",
    ) -> None:
        """Log plugin lifecycle events (init, start, stop, reload, error)."""
        self.log(
            event="plugin_lifecycle",
            plugin_id=plugin_id,
            detail=f"{action}: {detail}" if detail else action,
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        plugin_id: str = "",
        event: str = "",
        allowed: bool | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Query audit log with optional filters."""
        results = self._entries
        if plugin_id:
            results = [e for e in results if e["plugin_id"] == plugin_id]
        if event:
            results = [e for e in results if e["event"] == event]
        if allowed is not None:
            results = [e for e in results if e["allowed"] == allowed]
        return results[-limit:]

    def get_plugin_activity(self, plugin_id: str) -> dict[str, int]:
        """Get activity summary for a plugin."""
        entries = [e for e in self._entries if e["plugin_id"] == plugin_id]
        summary: dict[str, int] = {}
        for e in entries:
            key = e["event"]
            summary[key] = summary.get(key, 0) + 1
        return summary

    def get_denied_summary(self) -> list[dict[str, Any]]:
        """Get summary of denied actions grouped by plugin."""
        denied = [e for e in self._entries if not e["allowed"]]
        by_plugin: dict[str, list[str]] = {}
        for e in denied:
            pid = e["plugin_id"] or "(anonymous)"
            by_plugin.setdefault(pid, []).append(e["permission"])
        return [
            {"plugin_id": pid, "denied_count": len(perms), "permissions": list(set(perms))}
            for pid, perms in by_plugin.items()
        ]

    @property
    def total_entries(self) -> int:
        return len(self._entries)

    @property
    def recent(self) -> list[AuditEntry]:
        """Last 50 entries."""
        return self._entries[-50:]

    def clear(self) -> None:
        self._entries.clear()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
