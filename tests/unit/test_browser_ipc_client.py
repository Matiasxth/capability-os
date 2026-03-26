from __future__ import annotations

import shutil
import textwrap
import unittest
from pathlib import Path

from system.tools.browser_ipc import BrowserIPCClient, BrowserIPCError

ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tests" / "unit" / ".tmp_runtime" / "browser_ipc_client"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


FAKE_WORKER_SCRIPT = textwrap.dedent(
    """
    import argparse
    import json
    import sys
    import time
    import uuid
    from datetime import datetime, timezone

    def now():
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def base_response(request):
        return {
            "protocol_version": "1.0",
            "message_type": "response",
            "request_id": request["request_id"],
            "timestamp": now(),
            "source": "browser_worker",
            "target": request.get("source", "backend"),
            "action": request.get("action", "unknown"),
            "session_id": request.get("session_id"),
            "payload": {},
            "metadata": {"duration_ms": 1},
        }

    def send(message):
        sys.stdout.write(json.dumps(message, ensure_ascii=True) + "\\n")
        sys.stdout.flush()

    def main():
        parser = argparse.ArgumentParser()
        parser.add_argument("--workspace-root", required=True)
        parser.parse_args()

        sessions = {}
        active_session = None
        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue
            request = json.loads(line)
            msg_type = request["message_type"]

            if msg_type == "health":
                response = base_response(request)
                response["status"] = "success"
                response["result"] = {"status": "ready"}
                response["error"] = None
                send(response)
                continue

            if msg_type == "control":
                response = base_response(request)
                response["status"] = "success"
                response["result"] = {"status": "shutting_down"}
                response["error"] = None
                send(response)
                if request.get("action") == "shutdown":
                    break
                continue

            action = request.get("action")
            if action == "sleep_action":
                time.sleep(0.3)
                response = base_response(request)
                response["status"] = "success"
                response["result"] = {"status": "ok"}
                response["error"] = None
                send(response)
                continue

            if action == "error_action":
                response = base_response(request)
                response["status"] = "error"
                response["result"] = {}
                response["error"] = {
                    "error_code": "navigation_failed",
                    "error_message": "Navigation failed in fake worker.",
                    "details": {},
                }
                send(response)
                continue

            if action == "browser_open_session":
                session_id = f"session_fake_{uuid.uuid4().hex[:8]}"
                sessions[session_id] = {"url": "about:blank"}
                active_session = session_id
                response = base_response(request)
                response["session_id"] = session_id
                response["status"] = "success"
                response["result"] = {"status": "success", "session_id": session_id}
                response["error"] = None
                send(response)
                continue

            if action == "browser_navigate":
                session_id = request.get("session_id") or active_session
                if session_id not in sessions:
                    response = base_response(request)
                    response["status"] = "error"
                    response["result"] = {}
                    response["error"] = {
                        "error_code": "session_not_available",
                        "error_message": "Session not available.",
                        "details": {},
                    }
                    send(response)
                    continue

                url = request.get("payload", {}).get("url", "")
                sessions[session_id]["url"] = url
                active_session = session_id
                response = base_response(request)
                response["session_id"] = session_id
                response["status"] = "success"
                response["result"] = {
                    "status": "success",
                    "session_id": session_id,
                    "url": url,
                    "status_code": 200,
                }
                response["error"] = None
                send(response)
                continue

            response = base_response(request)
            response["status"] = "success"
            response["result"] = {"echo_action": action, "payload": request.get("payload", {})}
            response["error"] = None
            send(response)

    if __name__ == "__main__":
        main()
    """
)

EXIT_WORKER_SCRIPT = textwrap.dedent(
    """
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", required=True)
    parser.parse_args()
    """
)


class BrowserIPCClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case_dir = TMP_ROOT / self._testMethodName
        if self.case_dir.exists():
            shutil.rmtree(self.case_dir)
        self.case_dir.mkdir(parents=True, exist_ok=True)
        self.workspace = self.case_dir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

    def _write_script(self, name: str, content: str) -> Path:
        script_path = self.case_dir / name
        script_path.write_text(content, encoding="utf-8")
        return script_path

    def test_valid_request_and_response(self) -> None:
        worker_script = self._write_script("fake_worker.py", FAKE_WORKER_SCRIPT)
        client = BrowserIPCClient(worker_script_path=worker_script, workspace_root=self.workspace)
        self.addCleanup(client.shutdown)

        opened = client.execute(action="browser_open_session", payload={"headless": True})
        session_id = opened["session_id"]
        self.assertTrue(session_id.startswith("session_fake_"))

        navigated = client.execute(
            action="browser_navigate",
            payload={"url": "https://example.org/"},
            session_id=session_id,
        )
        self.assertEqual(navigated["status"], "success")
        self.assertEqual(navigated["url"], "https://example.org/")
        self.assertEqual(navigated["session_id"], session_id)

    def test_error_response_is_mapped(self) -> None:
        worker_script = self._write_script("fake_worker.py", FAKE_WORKER_SCRIPT)
        client = BrowserIPCClient(worker_script_path=worker_script, workspace_root=self.workspace)
        self.addCleanup(client.shutdown)

        with self.assertRaises(BrowserIPCError) as ctx:
            client.execute(action="error_action", payload={})
        self.assertEqual(ctx.exception.error_code, "navigation_failed")
        self.assertIn("fake worker", ctx.exception.error_message.lower())

    def test_timeout_is_mapped(self) -> None:
        worker_script = self._write_script("fake_worker.py", FAKE_WORKER_SCRIPT)
        client = BrowserIPCClient(worker_script_path=worker_script, workspace_root=self.workspace)
        self.addCleanup(client.shutdown)

        with self.assertRaises(BrowserIPCError) as ctx:
            client.execute(action="sleep_action", payload={}, timeout_ms=50)
        self.assertEqual(ctx.exception.error_code, "browser_worker_timeout")

    def test_worker_down_maps_to_unavailable(self) -> None:
        worker_script = self._write_script("exit_worker.py", EXIT_WORKER_SCRIPT)
        client = BrowserIPCClient(worker_script_path=worker_script, workspace_root=self.workspace)
        self.addCleanup(client.shutdown)

        with self.assertRaises(BrowserIPCError) as ctx:
            client.execute(action="browser_open_session", payload={})
        self.assertEqual(ctx.exception.error_code, "browser_worker_unavailable")

    def test_real_worker_main_bootstrap_imports_project_package(self) -> None:
        worker_script = ROOT / "system" / "browser_worker" / "worker_main.py"
        client = BrowserIPCClient(worker_script_path=worker_script, workspace_root=self.workspace)
        self.addCleanup(client.shutdown)

        health = client.health_check(timeout_ms=15000)
        self.assertEqual(health["status"], "ready")
        self.assertIn("session_count", health)


if __name__ == "__main__":
    unittest.main()
