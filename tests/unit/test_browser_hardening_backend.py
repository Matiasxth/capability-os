from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from typing import Any

from system.core.ui_bridge.api_server import CapabilityOSUIBridgeService
from system.tools.browser_ipc import BrowserIPCError
from system.tools.runtime import register_phase9_browser_tools

ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tests" / "unit" / ".tmp_runtime" / "browser_hardening_backend"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


class _MockIPCClient:
    def __init__(self, fail_actions: dict[str, BrowserIPCError] | None = None):
        self.fail_actions = fail_actions or {}
        self.session_counter = 0
        self.active_session_id: str | None = None
        self.sessions: dict[str, dict[str, Any]] = {}
        self._max_restart_retries = 2

    def set_max_restart_retries(self, value: int) -> None:
        self._max_restart_retries = max(0, int(value))

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
        forced_error = self.fail_actions.get(action)
        if forced_error is not None:
            raise forced_error

        if action == "browser_open_session":
            self.session_counter += 1
            new_session_id = f"session_mock_{self.session_counter}"
            self.sessions[new_session_id] = {
                "url": payload.get("start_url", "about:blank"),
                "interactive_elements": [
                    {
                        "element_id": "el_001",
                        "type": "button",
                        "text": "Send",
                        "aria_label": "",
                        "placeholder": "",
                        "selector": "#send",
                        "xpath": "/html/body/button[1]",
                        "visible": True,
                        "enabled": True,
                        "bounding_box": {"x": 10, "y": 20, "width": 120, "height": 32},
                        "in_viewport": True,
                        "tag": "button",
                        "attributes": {"id": "send", "class": "btn", "role": "button", "type": "button"},
                    },
                    {
                        "element_id": "el_002",
                        "type": "input",
                        "text": "",
                        "aria_label": "",
                        "placeholder": "Message",
                        "selector": "#message",
                        "xpath": "/html/body/input[1]",
                        "visible": True,
                        "enabled": True,
                        "bounding_box": {"x": 10, "y": 60, "width": 220, "height": 30},
                        "in_viewport": True,
                        "tag": "input",
                        "attributes": {"id": "message", "class": "", "role": "", "type": "text"},
                    },
                ],
            }
            self.active_session_id = new_session_id
            result = {"status": "success", "session_id": new_session_id}
            if isinstance(payload.get("start_url"), str) and payload["start_url"]:
                result["url"] = payload["start_url"]
                result["status_code"] = 200
            return result

        resolved_session = self._resolve_session_id(session_id)
        if action == "browser_navigate":
            url = payload.get("url")
            self.sessions[resolved_session]["url"] = url
            return {"status": "success", "session_id": resolved_session, "url": url, "status_code": 200}

        if action == "browser_read_text":
            return {
                "status": "success",
                "session_id": resolved_session,
                "text": f"Body for {self.sessions[resolved_session]['url']}",
                "url": self.sessions[resolved_session]["url"],
            }

        if action == "browser_list_interactive_elements":
            rows = list(self.sessions[resolved_session]["interactive_elements"])
            filters = payload.get("filters", {})
            if isinstance(filters, dict):
                if filters.get("visible_only", True):
                    rows = [row for row in rows if row.get("visible", False)]
                if filters.get("in_viewport_only", False):
                    rows = [row for row in rows if row.get("in_viewport", False)]
                text_contains = filters.get("text_contains")
                if isinstance(text_contains, str) and text_contains:
                    needle = text_contains.lower()
                    rows = [
                        row
                        for row in rows
                        if needle in str(row.get("text", "")).lower()
                        or needle in str(row.get("aria_label", "")).lower()
                        or needle in str(row.get("placeholder", "")).lower()
                    ]
            return {
                "status": "success",
                "session_id": resolved_session,
                "elements": rows,
                "count": len(rows),
            }

        if action == "browser_click_element_by_id":
            element_id = payload.get("element_id")
            target = next(
                (
                    row
                    for row in self.sessions[resolved_session]["interactive_elements"]
                    if row["element_id"] == element_id
                ),
                None,
            )
            if target is None:
                raise BrowserIPCError(
                    "element_not_found",
                    f"Element '{element_id}' was not found for session '{resolved_session}'.",
                )
            return {
                "status": "success",
                "session_id": resolved_session,
                "element_id": element_id,
                "selector": target["selector"],
                "url": self.sessions[resolved_session]["url"],
            }

        if action == "browser_close_session":
            self.sessions.pop(resolved_session, None)
            if self.active_session_id == resolved_session:
                self.active_session_id = None
            return {"status": "success", "session_id": resolved_session}

        return {"status": "success", "session_id": resolved_session}

    def _resolve_session_id(self, session_id: str | None) -> str:
        resolved = session_id or self.active_session_id
        if not isinstance(resolved, str) or not resolved:
            raise BrowserIPCError("session_not_available", "No active session.")
        if resolved not in self.sessions:
            raise BrowserIPCError("session_not_available", f"Session '{resolved}' does not exist.")
        self.active_session_id = resolved
        return resolved


class BrowserHardeningBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case_dir = TMP_ROOT / self._testMethodName
        if self.case_dir.exists():
            shutil.rmtree(self.case_dir)
        self.case_dir.mkdir(parents=True, exist_ok=True)
        self.workspace = self.case_dir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

    def _build_service(self, ipc_client: _MockIPCClient) -> CapabilityOSUIBridgeService:
        service = CapabilityOSUIBridgeService(workspace_root=self.workspace)
        register_phase9_browser_tools(service.tool_runtime, self.workspace, ipc_client=ipc_client)
        return service

    def test_open_then_navigate_in_separate_requests(self) -> None:
        service = self._build_service(_MockIPCClient())

        opened = service.handle("POST", "/execute", {"capability_id": "open_browser", "inputs": {"headless": True}})
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(opened.payload["status"], "success")
        session_id = opened.payload["final_output"]["session_id"]

        navigated = service.handle(
            "POST",
            "/execute",
            {
                "capability_id": "navigate_web",
                "inputs": {"session_id": session_id, "url": "https://example.org/"},
            },
        )
        self.assertEqual(navigated.status_code, 200)
        self.assertEqual(navigated.payload["status"], "success")
        self.assertEqual(navigated.payload["final_output"]["session_id"], session_id)
        self.assertEqual(navigated.payload["final_output"]["url"], "https://example.org/")

    def test_multiple_sessions_are_supported(self) -> None:
        service = self._build_service(_MockIPCClient())

        first = service.handle("POST", "/execute", {"capability_id": "open_browser", "inputs": {"headless": True}})
        second = service.handle("POST", "/execute", {"capability_id": "open_browser", "inputs": {"headless": True}})
        self.assertEqual(first.payload["status"], "success")
        self.assertEqual(second.payload["status"], "success")
        first_session_id = first.payload["final_output"]["session_id"]
        second_session_id = second.payload["final_output"]["session_id"]
        self.assertNotEqual(first_session_id, second_session_id)

        nav_first = service.handle(
            "POST",
            "/execute",
            {
                "capability_id": "navigate_web",
                "inputs": {"session_id": first_session_id, "url": "https://first.example/"},
            },
        )
        nav_second = service.handle(
            "POST",
            "/execute",
            {
                "capability_id": "navigate_web",
                "inputs": {"session_id": second_session_id, "url": "https://second.example/"},
            },
        )
        self.assertEqual(nav_first.payload["status"], "success")
        self.assertEqual(nav_second.payload["status"], "success")
        self.assertEqual(nav_first.payload["final_output"]["session_id"], first_session_id)
        self.assertEqual(nav_second.payload["final_output"]["session_id"], second_session_id)

    def test_worker_unavailable_is_surfaceable(self) -> None:
        service = self._build_service(
            _MockIPCClient(
                fail_actions={
                    "browser_open_session": BrowserIPCError(
                        "browser_worker_unavailable",
                        "Browser worker is unavailable.",
                    )
                }
            )
        )

        response = service.handle(
            "POST",
            "/execute",
            {"capability_id": "open_browser", "inputs": {"headless": True}},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload["status"], "error")
        self.assertEqual(response.payload["error_code"], "tool_execution_error")
        self.assertIn("browser_worker_unavailable", response.payload["error_message"])

    def test_worker_timeout_is_surfaceable(self) -> None:
        service = self._build_service(
            _MockIPCClient(
                fail_actions={
                    "browser_navigate": BrowserIPCError(
                        "browser_worker_timeout",
                        "Browser worker timeout.",
                    )
                }
            )
        )

        opened = service.handle("POST", "/execute", {"capability_id": "open_browser", "inputs": {"headless": True}})
        session_id = opened.payload["final_output"]["session_id"]
        response = service.handle(
            "POST",
            "/execute",
            {
                "capability_id": "navigate_web",
                "inputs": {"session_id": session_id, "url": "https://timeout.example/"},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload["status"], "error")
        self.assertEqual(response.payload["error_code"], "tool_execution_error")
        self.assertIn("browser_worker_timeout", response.payload["error_message"])

    def test_list_interactive_elements_and_click_by_id(self) -> None:
        service = self._build_service(_MockIPCClient())
        opened = service.handle("POST", "/execute", {"capability_id": "open_browser", "inputs": {"headless": True}})
        session_id = opened.payload["final_output"]["session_id"]

        listed = service.handle(
            "POST",
            "/execute",
            {
                "capability_id": "browser_list_interactive_elements",
                "inputs": {"session_id": session_id, "filters": {"visible_only": True}},
            },
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.payload["status"], "success")
        self.assertGreaterEqual(listed.payload["final_output"]["count"], 1)
        element_id = listed.payload["final_output"]["elements"][0]["element_id"]

        clicked = service.handle(
            "POST",
            "/execute",
            {
                "capability_id": "browser_click_element_by_id",
                "inputs": {"session_id": session_id, "element_id": element_id},
            },
        )
        self.assertEqual(clicked.status_code, 200)
        self.assertEqual(clicked.payload["status"], "success")
        self.assertEqual(clicked.payload["final_output"]["element_id"], element_id)

    def test_click_by_invalid_element_id_returns_structured_error(self) -> None:
        service = self._build_service(_MockIPCClient())
        opened = service.handle("POST", "/execute", {"capability_id": "open_browser", "inputs": {"headless": True}})
        session_id = opened.payload["final_output"]["session_id"]

        response = service.handle(
            "POST",
            "/execute",
            {
                "capability_id": "browser_click_element_by_id",
                "inputs": {"session_id": session_id, "element_id": "el_999"},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload["status"], "error")
        self.assertEqual(response.payload["error_code"], "tool_execution_error")
        self.assertIn("element_not_found", response.payload["error_message"])


if __name__ == "__main__":
    unittest.main()
