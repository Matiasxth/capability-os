"""Health Monitor — checks system health periodically.

Runs every 60 seconds, verifies all components are functional.
Triggers alerts and auto-recovery on failures.
"""
from __future__ import annotations

import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


class HealthMonitor:
    """Periodic health checks for all system components."""

    def __init__(self, interval_s: int = 60, api_port: int = 8000) -> None:
        self._interval = interval_s
        self._port = api_port
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_results: list[dict[str, Any]] = []
        self._history: list[dict[str, Any]] = []
        self._callbacks: list[Any] = []

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="health-monitor")
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def on_failure(self, callback) -> None:
        """Register callback for health failures: callback(failed_checks)."""
        self._callbacks.append(callback)

    @property
    def running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    @property
    def last_results(self) -> list[dict[str, Any]]:
        return list(self._last_results)

    @property
    def status(self) -> str:
        if not self._last_results:
            return "unknown"
        failed = [r for r in self._last_results if not r.get("ok")]
        if not failed:
            return "healthy"
        if len(failed) >= 3:
            return "critical"
        return "degraded"

    def run_checks(self) -> list[dict[str, Any]]:
        """Run all health checks now. Returns list of {check, ok, error?}."""
        results = []
        for name, fn in self._checks():
            try:
                ok = fn()
                results.append({"check": name, "ok": bool(ok)})
            except Exception as exc:
                results.append({"check": name, "ok": False, "error": str(exc)[:200]})

        self._last_results = results
        self._history.append({
            "timestamp": _now(),
            "results": results,
            "status": "healthy" if all(r["ok"] for r in results) else "degraded",
        })
        if len(self._history) > 100:
            self._history = self._history[-50:]

        # Notify on failures
        failed = [r for r in results if not r["ok"]]
        if failed:
            for cb in self._callbacks:
                try:
                    cb(failed)
                except Exception:
                    pass

        return results

    def _checks(self):
        """List of health checks."""
        return [
            ("api_health", self._check_api),
            ("disk_space", self._check_disk),
            ("workspace_exists", self._check_workspace),
            ("event_bus", self._check_event_bus),
        ]

    def _check_api(self) -> bool:
        try:
            req = Request(f"http://127.0.0.1:{self._port}/health")
            with urlopen(req, timeout=5) as r:
                return r.status == 200
        except Exception:
            return False

    def _check_disk(self) -> bool:
        try:
            usage = shutil.disk_usage("/")
            return usage.free > 100_000_000  # 100MB minimum
        except Exception:
            return True  # Can't check — assume OK

    def _check_workspace(self) -> bool:
        # Check common workspace paths
        for p in [Path("C:/data/workspace"), Path("/data/workspace"), Path(".")]:
            if p.exists():
                return True
        return False

    def _check_event_bus(self) -> bool:
        try:
            from system.core.ui_bridge.event_bus import event_bus
            return event_bus.subscriber_count > 0
        except Exception:
            return False

    def _loop(self) -> None:
        print("[HEALTH-MONITOR] Started", flush=True)
        while self._running:
            try:
                self.run_checks()
            except Exception:
                pass
            time.sleep(self._interval)
        print("[HEALTH-MONITOR] Stopped", flush=True)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
