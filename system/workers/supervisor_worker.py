#!/usr/bin/env python3
"""Supervisor worker — runs as separate process.

Monitors system health, detects capability gaps, audits security.
Reports findings via Redis events to the main process.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def main() -> None:
    from system.workers.base import BaseWorker

    class SupervisorWorker(BaseWorker):
        worker_name = "supervisor_worker"
        pool_size = 2

        def run(self) -> None:
            settings = self.load_settings()
            import os
            workspace_root = Path(os.environ.get("CAPOS_PROJECT_ROOT", "."))

            # Set up health monitor
            health_checks = []
            try:
                from system.core.supervisor.health_monitor import HealthMonitor
                health_monitor = HealthMonitor(workspace_root=workspace_root)
                health_checks.append(("health", health_monitor))
                logger.info("HealthMonitor ready")
            except Exception as exc:
                logger.warning("HealthMonitor not available: %s", exc)

            # Set up gap detector
            try:
                from system.core.supervisor.gap_detector import GapDetector
                gap_detector = GapDetector(workspace_root=workspace_root)
                health_checks.append(("gap", gap_detector))
                logger.info("GapDetector ready")
            except Exception as exc:
                logger.warning("GapDetector not available: %s", exc)

            # Set up security auditor
            try:
                from system.core.supervisor.security_auditor import SecurityAuditor
                security_auditor = SecurityAuditor(workspace_root=workspace_root)
                health_checks.append(("security", security_auditor))
                logger.info("SecurityAuditor ready")
            except Exception as exc:
                logger.warning("SecurityAuditor not available: %s", exc)

            # Subscribe to error events for error interception
            error_count = 0

            logger.info("Supervisor worker started (%d monitors)", len(health_checks))

            HEALTH_INTERVAL = 300    # 5 min
            GAP_INTERVAL = 1800      # 30 min
            SECURITY_INTERVAL = 3600 # 1 hour

            last_health = 0.0
            last_gap = 0.0
            last_security = 0.0

            while self._running:
                now = time.time()
                self.heartbeat()

                # Health check cycle
                if now - last_health >= HEALTH_INTERVAL:
                    last_health = now
                    for name, monitor in health_checks:
                        if name == "health":
                            self._pool.submit(self._run_health_check, monitor)

                # Gap detection cycle
                if now - last_gap >= GAP_INTERVAL:
                    last_gap = now
                    for name, monitor in health_checks:
                        if name == "gap":
                            self._pool.submit(self._run_gap_detection, monitor)

                # Security audit cycle
                if now - last_security >= SECURITY_INTERVAL:
                    last_security = now
                    for name, monitor in health_checks:
                        if name == "security":
                            self._pool.submit(self._run_security_audit, monitor)

                time.sleep(30)

            logger.info("Supervisor worker stopped")

        def _run_health_check(self, monitor: Any) -> None:
            try:
                result = monitor.check()
                failed = [c for c in (result.get("checks", []) if isinstance(result, dict) else []) if not c.get("ok")]
                if failed:
                    self._queue.publish("capos:events:supervisor_alert", {
                        "type": "supervisor_alert",
                        "data": {"severity": "warning", "source": "health_monitor", "failed_checks": [c.get("check") for c in failed]},
                    })
                    logger.warning("Health check: %d failed", len(failed))
            except Exception as exc:
                logger.error("Health check error: %s", exc)

        def _run_gap_detection(self, detector: Any) -> None:
            try:
                summary = detector.get_summary() if hasattr(detector, "get_summary") else {}
                if summary.get("total_gaps", 0) > 0:
                    self._queue.publish("capos:events:supervisor_alert", {
                        "type": "supervisor_alert",
                        "data": {"severity": "info", "source": "gap_detector", "message": f"{summary['total_gaps']} capability gaps detected"},
                    })
            except Exception as exc:
                logger.error("Gap detection error: %s", exc)

        def _run_security_audit(self, auditor: Any) -> None:
            try:
                result = auditor.audit() if hasattr(auditor, "audit") else {}
                findings = result.get("findings", 0) if isinstance(result, dict) else 0
                if findings > 0:
                    self._queue.publish("capos:events:supervisor_alert", {
                        "type": "supervisor_alert",
                        "data": {"severity": "high", "source": "security_auditor", "findings": findings, "message": f"{findings} security issues found"},
                    })
                    logger.warning("Security audit: %d findings", findings)
            except Exception as exc:
                logger.error("Security audit error: %s", exc)

    worker = SupervisorWorker()
    worker.bootstrap()
    worker.run()
    worker.shutdown()


if __name__ == "__main__":
    main()
