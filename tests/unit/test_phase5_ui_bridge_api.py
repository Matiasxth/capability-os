from __future__ import annotations

import json
import shutil
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from system.core.ui_bridge import create_http_server

ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tests" / "unit" / ".tmp_runtime" / "phase5_ui_bridge"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


def _request(base_url: str, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(f"{base_url}{path}", data=data, method=method, headers=headers)
    try:
        with urlopen(request) as response:
            body = response.read().decode("utf-8")
            return int(response.status), json.loads(body)
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        exc.close()
        return int(exc.code), json.loads(body)


class Phase5UIBridgeAPITests(unittest.TestCase):
    def setUp(self) -> None:
        self.case_dir = TMP_ROOT / self._testMethodName
        if self.case_dir.exists():
            shutil.rmtree(self.case_dir)
        self.case_dir.mkdir(parents=True, exist_ok=True)
        self.workspace = self.case_dir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        (self.workspace / "demo.txt").write_text("phase5 demo", encoding="utf-8-sig")

        self.server = create_http_server(host="127.0.0.1", port=0, workspace_root=self.workspace)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.base_url = f"http://{host}:{port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_get_capabilities_endpoint(self) -> None:
        status, payload = _request(self.base_url, "GET", "/capabilities")

        self.assertEqual(status, 200)
        self.assertIn("capabilities", payload)
        capability_ids = {item["id"] for item in payload["capabilities"]}
        self.assertIn("read_file", capability_ids)
        self.assertIn("create_project", capability_ids)

    def test_get_status_endpoint(self) -> None:
        status, payload = _request(self.base_url, "GET", "/status")
        self.assertEqual(status, 200)
        self.assertIn("llm", payload)
        self.assertIn("browser_worker", payload)
        self.assertIn("integrations", payload)
        self.assertTrue(payload["llm"]["suggest_only"])

    def test_get_capability_detail_endpoint(self) -> None:
        status, payload = _request(self.base_url, "GET", "/capabilities/read_file")

        self.assertEqual(status, 200)
        capability = payload["capability"]
        self.assertEqual(capability["id"], "read_file")
        self.assertIn("inputs", capability)
        self.assertIn("outputs", capability)

    def test_execute_and_query_execution_endpoints(self) -> None:
        status, execute_payload = _request(
            self.base_url,
            "POST",
            "/execute",
            {
                "capability_id": "read_file",
                "inputs": {"path": "demo.txt"},
            },
        )

        self.assertEqual(status, 200)
        self.assertEqual(execute_payload["status"], "success")
        execution_id = execute_payload["execution_id"]
        self.assertIsInstance(execution_id, str)
        self.assertTrue(execution_id.startswith("exec_"))

        runtime = execute_payload["runtime"]
        self.assertEqual(runtime["execution_id"], execution_id)
        self.assertEqual(runtime["capability_id"], "read_file")
        self.assertIn(runtime["status"], {"ready", "error"})
        self.assertIn("logs", runtime)

        execution_status, execution_payload = _request(
            self.base_url,
            "GET",
            f"/executions/{execution_id}",
        )
        self.assertEqual(execution_status, 200)
        self.assertEqual(execution_payload["execution_id"], execution_id)
        self.assertIn("runtime", execution_payload)

        events_status, events_payload = _request(
            self.base_url,
            "GET",
            f"/executions/{execution_id}/events",
        )
        self.assertEqual(events_status, 200)
        events = events_payload["events"]
        self.assertTrue(any(event["event"] == "execution_started" for event in events))
        self.assertTrue(any(event["event"] == "execution_finished" for event in events))

    def test_execute_invalid_capability_returns_structured_error(self) -> None:
        status, payload = _request(
            self.base_url,
            "POST",
            "/execute",
            {"capability_id": "unknown_capability", "inputs": {}},
        )

        self.assertEqual(status, 404)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error_code"], "capability_not_found")
        self.assertIn("unknown_capability", payload["error_message"])

    def test_execute_validation_error_returns_structured_error(self) -> None:
        status, payload = _request(
            self.base_url,
            "POST",
            "/execute",
            {"capability_id": "read_file", "inputs": {}},
        )

        self.assertEqual(status, 400)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error_code"], "validation_error")


if __name__ == "__main__":
    unittest.main()
