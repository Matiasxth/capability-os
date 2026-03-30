"""Python IPC client for the Baileys-based WhatsApp worker.

Spawns ``worker.js`` as a subprocess and communicates via
stdin/stdout JSON lines — same pattern as the browser IPC client.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any


class WhatsAppClientError(RuntimeError):
    """Raised when the WhatsApp worker fails or times out."""

    def __init__(self, error_code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


_WORKER_DIR = Path(__file__).resolve().parent


class WhatsAppClient:
    """Manages the Baileys worker subprocess and provides a sync API."""

    def __init__(self, node_bin: str = "node", startup_timeout_s: float = 30.0, worker_script: str = "worker.js"):
        self._node_bin = node_bin
        self._startup_timeout_s = startup_timeout_s
        self._worker_script = worker_script
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.RLock()
        self._pending: dict[str, threading.Event] = {}
        self._results: dict[str, dict[str, Any]] = {}
        self._reader_thread: threading.Thread | None = None

        self._status: str = "disconnected"  # disconnected | connecting | connected
        self._qr: str | None = None
        self._user: dict[str, Any] | None = None
        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Launch the worker subprocess if not already running."""
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return
            worker_js = _WORKER_DIR / self._worker_script
            if not worker_js.exists():
                raise WhatsAppClientError("worker_not_found", f"Worker script not found at {worker_js}")
            self._status = "connecting"
            self._qr = None
            self._user = None
            try:
                self._process = subprocess.Popen(
                    [self._node_bin, str(worker_js)],
                    cwd=str(_WORKER_DIR),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    bufsize=1,
                )
            except Exception as _start_exc:
                raise WhatsAppClientError("worker_start_failed", f"Failed to start worker: {_start_exc}") from _start_exc
            self._started = True
            self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._reader_thread.start()
            # Read stderr in background for diagnostics
            threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stderr(self) -> None:
        proc = self._process
        if proc is None or proc.stderr is None:
            return
        for line in proc.stderr:
            line = line.strip()
            if line:
                print(f"[BAILEYS-STDERR] {line}", flush=True)

    def stop(self) -> None:
        with self._lock:
            proc = self._process
            self._process = None
            self._status = "disconnected"
            self._started = False
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    @property
    def alive(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        return {
            "connected": self._status == "connected",
            "status": self._status,
            "qr": self._qr,
            "user": self._user,
            "alive": self.alive,
        }

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def send_message(self, to: str, message: str, timeout_s: float = 30.0) -> dict[str, Any]:
        self._ensure_started()
        return self._send_command("send_message", {"to": to, "message": message}, timeout_s)

    def search_contact(self, query: str, timeout_s: float = 10.0) -> dict[str, Any]:
        self._ensure_started()
        return self._send_command("search_contact", {"query": query}, timeout_s)

    def get_qr(self, timeout_s: float = 5.0) -> str | None:
        if self._qr:
            return self._qr
        self._ensure_started()
        result = self._send_command("get_qr", {}, timeout_s)
        return result.get("qr")

    def request_status(self, timeout_s: float = 5.0) -> dict[str, Any]:
        self._ensure_started()
        return self._send_command("status", {}, timeout_s)

    def logout(self, timeout_s: float = 10.0) -> dict[str, Any]:
        self._ensure_started()
        result = self._send_command("logout", {}, timeout_s)
        self._status = "disconnected"
        self._qr = None
        self._user = None
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_started(self) -> None:
        if not self.alive:
            self.start()

    def _send_command(self, action: str, params: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        cmd_id = uuid.uuid4().hex[:8]
        event = threading.Event()
        with self._lock:
            self._pending[cmd_id] = event
            proc = self._process
        if proc is None or proc.stdin is None:
            raise WhatsAppClientError("worker_not_running", "WhatsApp worker is not running.")

        cmd = {"id": cmd_id, "action": action, **params}
        try:
            proc.stdin.write(json.dumps(cmd, ensure_ascii=True) + "\n")
            proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            with self._lock:
                self._pending.pop(cmd_id, None)
            raise WhatsAppClientError("worker_write_failed", f"Failed to write to worker: {exc}") from exc

        if not event.wait(timeout=timeout_s):
            with self._lock:
                self._pending.pop(cmd_id, None)
            raise WhatsAppClientError("worker_timeout", f"Worker did not respond within {timeout_s}s.")

        result = self._results.pop(cmd_id, {})
        if result.get("type") == "error":
            raise WhatsAppClientError("worker_error", result.get("error", "Unknown worker error"))
        return result

    def _read_loop(self) -> None:
        proc = self._process
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")
            msg_id = msg.get("id")

            # Handle status broadcasts
            if msg_type == "qr":
                self._qr = msg.get("qr") or msg.get("qr_image")
                self._status = "connecting"
            elif msg_type == "ready":
                self._status = "connected"
                self._qr = None
                self._user = msg.get("user")
            elif msg_type == "disconnected":
                self._status = "disconnected"
                self._user = None
            elif msg_type == "status" and not msg_id:
                self._status = msg.get("status", self._status)
            elif msg_type == "fatal":
                self._status = "error"
            elif msg_type == "incoming_message":
                try:
                    from system.core.ui_bridge.event_bus import event_bus
                    event_bus.emit("whatsapp_message", {
                        "from": msg.get("from", ""),
                        "pushName": msg.get("pushName", ""),
                        "text": (msg.get("text", ""))[:200],
                        "messageId": msg.get("messageId", ""),
                    })
                except Exception:
                    pass

            # Resolve pending command
            if msg_id:
                with self._lock:
                    event = self._pending.pop(msg_id, None)
                if event:
                    self._results[msg_id] = msg
                    event.set()
