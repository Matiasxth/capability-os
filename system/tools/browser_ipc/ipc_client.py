from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from .message_builder import (
    PROTOCOL_VERSION,
    build_command_message,
    build_control_message,
    build_health_message,
    utc_timestamp,
)
from .response_parser import IPCProtocolError, parse_message_line, parse_response_for_request


class BrowserIPCError(RuntimeError):
    """Structured error surfaced by IPC transport/client layer."""

    def __init__(self, error_code: str, error_message: str, details: dict[str, Any] | None = None):
        super().__init__(error_message)
        self.error_code = error_code
        self.error_message = error_message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "error_message": self.error_message,
            "details": self.details,
        }


class BrowserIPCClient:
    """JSON-over-stdio IPC client for browser worker process."""

    def __init__(
        self,
        *,
        worker_script_path: str | Path | None = None,
        workspace_root: str | Path | None = None,
        default_timeout_ms: int = 15000,
        startup_timeout_ms: int = 10000,
    ):
        default_worker_script = Path(__file__).resolve().parents[2] / "browser_worker" / "worker_main.py"
        self.worker_script_path = Path(worker_script_path or default_worker_script).resolve()
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.default_timeout_ms = default_timeout_ms
        self.startup_timeout_ms = startup_timeout_ms

        self._state_lock = threading.RLock()
        self._write_lock = threading.RLock()
        self._process: subprocess.Popen[str] | None = None
        self._stdout_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._pending: dict[str, queue.Queue[dict[str, Any]]] = {}
        self._events: list[dict[str, Any]] = []
        self._stderr_lines: list[str] = []
        self._worker_failed = False
        self._closed = False
        self._start_attempted = False
        self._dead_reason: str | None = None

    def execute(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        session_id: str | None = None,
        timeout_ms: int | None = None,
        transport_timeout_ms: int | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        effective_timeout = _resolve_timeout_ms(timeout_ms, self.default_timeout_ms)
        effective_transport_timeout = _resolve_timeout_ms(
            transport_timeout_ms,
            effective_timeout,
        )
        message = build_command_message(
            action=action,
            payload=payload,
            session_id=session_id,
            timeout_ms=effective_timeout,
            trace_id=trace_id,
        )
        return self._send_request(message, effective_transport_timeout)

    def health_check(self, timeout_ms: int | None = None) -> dict[str, Any]:
        effective_timeout = _resolve_timeout_ms(timeout_ms, self.startup_timeout_ms)
        message = build_health_message()
        return self._send_request(message, effective_timeout)

    def shutdown(self, timeout_ms: int | None = None) -> None:
        effective_timeout = _resolve_timeout_ms(timeout_ms, self.default_timeout_ms)
        with self._state_lock:
            process = self._process
        if process is None or process.poll() is not None:
            self._closed = True
            return
        try:
            self._send_request(build_control_message(action="shutdown"), effective_timeout)
        except Exception:
            pass
        finally:
            self._closed = True
            self._terminate_process()

    def restart(self, timeout_ms: int | None = None) -> None:
        self.shutdown(timeout_ms=timeout_ms)
        with self._state_lock:
            self._closed = False
            self._worker_failed = False
            self._dead_reason = None
            self._start_attempted = False
            self._events = []
            self._stderr_lines = []

    def get_status(self) -> dict[str, Any]:
        with self._state_lock:
            process = self._process
            alive = process is not None and process.poll() is None
            return {
                "alive": alive,
                "worker_failed": self._worker_failed,
                "closed": self._closed,
                "dead_reason": self._dead_reason,
                "stderr_tail": list(self._stderr_lines[-20:]),
            }

    def drain_events(self) -> list[dict[str, Any]]:
        with self._state_lock:
            drained = list(self._events)
            self._events = []
        return drained

    def _send_request(self, message: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        self._ensure_started()
        request_id = message["request_id"]
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)

        with self._state_lock:
            process = self._process
            if process is None or process.poll() is not None:
                raise BrowserIPCError(
                    "browser_worker_unavailable",
                    "Browser worker process is not available.",
                    self._transport_details(),
                )
            self._pending[request_id] = response_queue

        try:
            raw = json.dumps(message, ensure_ascii=True)
            with self._write_lock:
                if process.stdin is None:
                    raise BrowserIPCError(
                        "browser_worker_unavailable",
                        "Browser worker stdin is not available.",
                        self._transport_details(),
                    )
                process.stdin.write(raw + "\n")
                process.stdin.flush()
        except BrowserIPCError:
            with self._state_lock:
                self._pending.pop(request_id, None)
            raise
        except Exception as exc:
            with self._state_lock:
                self._pending.pop(request_id, None)
            self._mark_worker_dead(f"write_failed: {exc}")
            raise BrowserIPCError(
                "browser_worker_unavailable",
                f"Failed to write request to browser worker: {exc}",
                self._transport_details(),
            ) from exc

        try:
            response_message = response_queue.get(timeout=timeout_ms / 1000)
        except queue.Empty as exc:
            with self._state_lock:
                self._pending.pop(request_id, None)
            raise BrowserIPCError(
                "browser_worker_timeout",
                f"Browser worker did not respond within {timeout_ms} ms.",
                {"request_id": request_id, **self._transport_details()},
            ) from exc
        finally:
            with self._state_lock:
                self._pending.pop(request_id, None)

        try:
            parsed = parse_response_for_request(response_message, request_id)
        except IPCProtocolError as exc:
            raise BrowserIPCError(
                "browser_worker_protocol_error",
                f"Invalid worker response: {exc}",
                {"request_id": request_id},
            ) from exc

        if parsed["status"] == "error":
            error = parsed["error"]
            raise BrowserIPCError(
                error["error_code"],
                error["error_message"],
                {
                    "request_id": request_id,
                    "worker_metadata": parsed["metadata"],
                    **error.get("details", {}),
                },
            )
        return parsed["result"]

    def _ensure_started(self) -> None:
        with self._state_lock:
            process = self._process
            if process is not None and process.poll() is None:
                return
            if self._closed:
                raise BrowserIPCError(
                    "browser_worker_unavailable",
                    "Browser worker client is closed.",
                    self._transport_details(),
                )
            if self._worker_failed:
                raise BrowserIPCError(
                    "browser_worker_unavailable",
                    f"Browser worker is unavailable: {self._dead_reason or 'unknown failure'}.",
                    self._transport_details(),
                )
            if self._start_attempted:
                raise BrowserIPCError(
                    "browser_worker_unavailable",
                    "Browser worker is not running and automatic restart is disabled in this phase.",
                    self._transport_details(),
                )
            self._start_worker_locked()
            self._start_attempted = True

    def _start_worker_locked(self) -> None:
        project_root_candidate = self.worker_script_path.parent.parent.parent
        if (project_root_candidate / "system").exists():
            launch_cwd = project_root_candidate
            pythonpath_prefix = str(project_root_candidate)
        else:
            launch_cwd = self.worker_script_path.parent
            pythonpath_prefix = str(launch_cwd)

        command = [
            sys.executable,
            str(self.worker_script_path),
            "--workspace-root",
            str(self.workspace_root),
        ]
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            pythonpath_prefix
            if not existing_pythonpath
            else f"{pythonpath_prefix}{os.pathsep}{existing_pythonpath}"
        )

        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                bufsize=1,
                cwd=str(launch_cwd),
                env=env,
            )
        except Exception as exc:
            self._worker_failed = True
            self._dead_reason = f"spawn_failed: {exc}"
            raise BrowserIPCError(
                "browser_worker_unavailable",
                f"Failed to start browser worker process: {exc}",
            ) from exc

        self._process = process
        self._stdout_thread = threading.Thread(
            target=self._stdout_reader_loop,
            name="browser-worker-stdout-reader",
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=self._stderr_reader_loop,
            name="browser-worker-stderr-reader",
            daemon=True,
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _stdout_reader_loop(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            self._mark_worker_dead("stdout_not_available")
            return

        try:
            for raw_line in process.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    message = parse_message_line(line)
                except IPCProtocolError as exc:
                    with self._state_lock:
                        self._events.append(
                            {
                                "protocol_version": PROTOCOL_VERSION,
                                "message_type": "event",
                                "request_id": "local",
                                "timestamp": utc_timestamp(),
                                "source": "ipc_client",
                                "target": "backend",
                                "action": "protocol_parse_error",
                                "session_id": None,
                                "payload": {},
                                "metadata": {"error": str(exc)},
                            }
                        )
                    continue

                message_type = message["message_type"]
                if message_type == "response":
                    request_id = message["request_id"]
                    with self._state_lock:
                        pending_queue = self._pending.get(request_id)
                    if pending_queue is not None:
                        pending_queue.put(message)
                    else:
                        with self._state_lock:
                            self._events.append(message)
                    continue

                with self._state_lock:
                    self._events.append(message)
        finally:
            self._mark_worker_dead("stdout_closed")

    def _stderr_reader_loop(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return
        for raw_line in process.stderr:
            line = raw_line.rstrip()
            if not line:
                continue
            with self._state_lock:
                self._stderr_lines.append(line)
                if len(self._stderr_lines) > 200:
                    self._stderr_lines = self._stderr_lines[-200:]

    def _mark_worker_dead(self, reason: str) -> None:
        with self._state_lock:
            if self._worker_failed:
                return
            self._worker_failed = True
            self._dead_reason = reason
            pending_ids = list(self._pending.keys())
            for request_id in pending_ids:
                pending_queue = self._pending.get(request_id)
                if pending_queue is None:
                    continue
                pending_queue.put(
                    {
                        "protocol_version": PROTOCOL_VERSION,
                        "message_type": "response",
                        "request_id": request_id,
                        "timestamp": utc_timestamp(),
                        "source": "browser_worker",
                        "target": "backend",
                        "action": "transport_failure",
                        "session_id": None,
                        "payload": {},
                        "metadata": {},
                        "status": "error",
                        "result": {},
                        "error": {
                            "error_code": "browser_worker_unavailable",
                            "error_message": f"Browser worker became unavailable ({reason}).",
                            "details": self._transport_details(),
                        },
                    }
                )

    def _transport_details(self) -> dict[str, Any]:
        with self._state_lock:
            process = self._process
            return {
                "worker_script_path": str(self.worker_script_path),
                "workspace_root": str(self.workspace_root),
                "process_pid": process.pid if process is not None else None,
                "process_returncode": process.poll() if process is not None else None,
                "dead_reason": self._dead_reason,
                "stderr_tail": list(self._stderr_lines[-10:]),
            }

    def _terminate_process(self) -> None:
        with self._state_lock:
            process = self._process
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1.5)
        except Exception:
            pass
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except Exception:
                    pass
            with self._state_lock:
                if self._process is process:
                    self._process = None


def _resolve_timeout_ms(value: int | None, default_value: int) -> int:
    timeout_ms = default_value if value is None else value
    if not isinstance(timeout_ms, int) or timeout_ms <= 0:
        raise BrowserIPCError(
            "invalid_timeout",
            "timeout_ms must be a positive integer.",
            {"timeout_ms": timeout_ms},
        )
    return timeout_ms
