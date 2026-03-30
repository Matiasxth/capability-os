"""Error notifier: watches for system errors and triggers Claude Code for auto-review.

Subscribes to the event bus and reacts to error events by:
1. Writing error details to errors/ directory
2. Launching ``claude -p`` to analyze and fix the issue

A cooldown prevents flooding Claude with rapid-fire errors.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_ERROR_EVENTS = {"error", "execution_complete"}


class ErrorNotifier:
    """Watches for system errors via event bus and triggers Claude Code review."""

    def __init__(
        self,
        project_root: Path,
        cooldown_seconds: int = 120,
        enabled: bool = True,
    ) -> None:
        self._project_root = project_root
        self._errors_dir = project_root / "errors"
        self._errors_dir.mkdir(exist_ok=True)
        self._cooldown = cooldown_seconds
        self._enabled = enabled
        self._last_trigger: float = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def subscribe(self, event_bus: Any) -> None:
        """Subscribe to error-related events on the event bus."""
        event_bus.subscribe(self._on_event)
        print(f"  ErrorNotifier: active (cooldown={self._cooldown}s)")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_event(self, event: dict[str, Any]) -> None:
        etype = event.get("type", "")
        if etype not in _ERROR_EVENTS:
            return

        data = event.get("data", {})

        if etype == "execution_complete" and data.get("status") != "error":
            return  # only react to failed executions

        if etype == "error":
            self._handle_error(
                source=data.get("source", "unknown"),
                error_code=data.get("error_code", "dispatch_error"),
                message=data.get("message", "Unknown error"),
                details=data,
            )
        else:  # execution_complete with error
            self._handle_error(
                source=f"capability:{data.get('capability_id', 'unknown')}",
                error_code=data.get("error_code", "execution_error"),
                message=data.get("error_message", "Capability execution failed"),
                details=data,
            )

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def _handle_error(
        self,
        source: str,
        error_code: str,
        message: str,
        details: dict[str, Any],
    ) -> None:
        timestamp = datetime.now(timezone.utc).isoformat()
        record = {
            "timestamp": timestamp,
            "source": source,
            "error_code": error_code,
            "message": message,
            "details": details,
        }

        error_file = self._write_error_log(record)
        print(f"[ErrorNotifier] Error detected: {error_code} from {source}")

        if self._enabled:
            self._trigger_claude(record, error_file)

    def _write_error_log(self, record: dict[str, Any]) -> Path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"{ts}_{record['error_code']}.json"
        filepath = self._errors_dir / filename
        filepath.write_text(
            json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8",
        )

        # Quick-access symlink-style copy
        latest = self._errors_dir / "latest_error.json"
        latest.write_text(
            json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8",
        )
        return filepath

    # ------------------------------------------------------------------
    # Claude Code trigger
    # ------------------------------------------------------------------

    def _trigger_claude(self, record: dict[str, Any], error_file: Path) -> None:
        with self._lock:
            now = time.monotonic()
            if now - self._last_trigger < self._cooldown:
                print("[ErrorNotifier] Cooldown active, skipping Claude trigger")
                return
            self._last_trigger = now

        prompt = (
            f"Se detecto un error en Capability OS que necesita revision.\n\n"
            f"Error code: {record['error_code']}\n"
            f"Source: {record['source']}\n"
            f"Message: {record['message']}\n\n"
            f"Archivo con detalles completos: {error_file}\n\n"
            f"Por favor:\n"
            f"1. Lee el archivo de error para ver los detalles completos\n"
            f"2. Analiza el codigo fuente relacionado en el proyecto\n"
            f"3. Identifica la causa raiz del error\n"
            f"4. Aplica la correccion necesaria en el codigo"
        )

        threading.Thread(
            target=self._run_claude,
            args=(prompt, record),
            daemon=True,
            name="claude-error-review",
        ).start()
        print(f"[ErrorNotifier] Claude Code triggered for: {record['error_code']}")

    def _run_claude(self, prompt: str, record: dict[str, Any]) -> None:
        log_file = self._errors_dir / "claude_review.log"
        try:
            with open(log_file, "a", encoding="utf-8") as log:
                log.write(f"\n{'=' * 60}\n")
                log.write(f"Review triggered at {record['timestamp']}\n")
                log.write(f"Error: {record['error_code']} | Source: {record['source']}\n")
                log.write(f"{'=' * 60}\n")

                result = subprocess.run(
                    ["claude", "-p", prompt],
                    cwd=str(self._project_root),
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                log.write(result.stdout or "")
                if result.stderr:
                    log.write(f"\nSTDERR:\n{result.stderr}")
                log.write(f"\n{'=' * 60}\n\n")

            print("[ErrorNotifier] Claude review complete. See errors/claude_review.log")
        except FileNotFoundError:
            print(
                "[ErrorNotifier] 'claude' CLI not found in PATH. "
                "Install: npm install -g @anthropic-ai/claude-code"
            )
        except subprocess.TimeoutExpired:
            print("[ErrorNotifier] Claude review timed out (5 min limit)")
        except Exception as exc:
            print(f"[ErrorNotifier] Claude trigger failed: {exc}")
