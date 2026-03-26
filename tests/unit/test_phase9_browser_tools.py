from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from typing import Any

from system.tools.browser_ipc import BrowserIPCError
from system.tools.implementations.phase9_browser_tools import BrowserToolError
from system.tools.registry import ToolRegistry
from system.tools.runtime import (
    ToolExecutionError,
    ToolRuntime,
    register_phase9_browser_tools,
)

ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tests" / "unit" / ".tmp_runtime" / "phase9_browser_tools"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


class _MockIPCClient:
    def __init__(self, *, fail_open: BrowserIPCError | None = None):
        self.fail_open = fail_open
        self.session_counter = 0
        self.active_session_id: str | None = None
        self.sessions: dict[str, dict[str, Any]] = {}

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
        if action == "browser_open_session":
            if self.fail_open is not None:
                raise self.fail_open
            self.session_counter += 1
            new_session_id = f"session_mock_{self.session_counter}"
            self.sessions[new_session_id] = {
                "tabs": [
                    {"url": payload.get("start_url", "about:blank"), "title": "Blank"},
                    {"url": "https://second.local/", "title": "Second"},
                ],
                "active_tab_index": 0,
                "elements": {"body": "Fake page body", "#name": "", "#submit": "Submit"},
                "interactive_elements": [
                    {
                        "element_id": "el_001",
                        "type": "button",
                        "text": "Submit",
                        "aria_label": "",
                        "placeholder": "",
                        "selector": "#submit",
                        "xpath": "/html/body/button[1]",
                        "visible": True,
                        "enabled": True,
                        "bounding_box": {"x": 10, "y": 20, "width": 120, "height": 30},
                        "in_viewport": True,
                        "tag": "button",
                        "attributes": {"id": "submit", "class": "", "role": "button", "type": "button"},
                    },
                    {
                        "element_id": "el_002",
                        "type": "input",
                        "text": "",
                        "aria_label": "",
                        "placeholder": "Name",
                        "selector": "#name",
                        "xpath": "/html/body/input[1]",
                        "visible": True,
                        "enabled": True,
                        "bounding_box": {"x": 10, "y": 60, "width": 180, "height": 28},
                        "in_viewport": True,
                        "tag": "input",
                        "attributes": {"id": "name", "class": "", "role": "", "type": "text"},
                    },
                ],
            }
            self.active_session_id = new_session_id
            result = {"status": "success", "session_id": new_session_id}
            if isinstance(payload.get("start_url"), str) and payload["start_url"]:
                result["url"] = payload["start_url"]
                result["status_code"] = 200
            return result

        if action == "browser_close_session":
            resolved_id = self._resolve_session_id(session_id)
            if resolved_id not in self.sessions:
                raise BrowserIPCError("session_not_available", f"Session '{resolved_id}' is not available.")
            self.sessions.pop(resolved_id)
            if self.active_session_id == resolved_id:
                self.active_session_id = next(iter(self.sessions), None) if self.sessions else None
            return {"status": "success", "session_id": resolved_id}

        resolved_id = self._resolve_session_id(session_id)
        state = self.sessions[resolved_id]
        tabs = state["tabs"]
        active_idx = state["active_tab_index"]
        active_tab = tabs[active_idx]

        if action == "browser_navigate":
            url = payload.get("url")
            if not isinstance(url, str) or not url:
                raise BrowserIPCError("invalid_input", "url is required")
            active_tab["url"] = url
            active_tab["title"] = f"Page {active_idx}"
            state["elements"]["body"] = f"Body for {url}"
            return {"status": "success", "session_id": resolved_id, "url": url, "status_code": 200}

        if action == "browser_click_element":
            selector = payload.get("selector")
            if selector == "#missing":
                raise BrowserIPCError("selector_not_found", "Selector '#missing' was not found.")
            return {"status": "success", "session_id": resolved_id, "selector": selector, "url": active_tab["url"]}

        if action == "browser_type_text":
            selector = payload.get("selector")
            if selector == "#missing":
                raise BrowserIPCError("selector_not_found", "Selector '#missing' was not found.")
            text = payload.get("text")
            state["elements"][selector] = text
            return {"status": "success", "session_id": resolved_id, "selector": selector, "url": active_tab["url"]}

        if action == "browser_read_text":
            selector = payload.get("selector") or "body"
            if selector == "#missing":
                raise BrowserIPCError("selector_not_found", "Selector '#missing' was not found.")
            return {
                "status": "success",
                "session_id": resolved_id,
                "text": state["elements"].get(selector, ""),
                "url": active_tab["url"],
            }

        if action == "browser_wait_for_selector":
            selector = payload.get("selector")
            if selector == "#missing":
                raise BrowserIPCError("selector_not_found", "Selector '#missing' was not found.")
            return {"status": "success", "session_id": resolved_id, "selector": selector, "url": active_tab["url"]}

        if action == "browser_take_screenshot":
            raw_path = payload.get("path")
            if not isinstance(raw_path, str) or not raw_path:
                raise BrowserIPCError("invalid_input", "path is required")
            screenshot_path = Path(raw_path)
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            screenshot_path.write_bytes(b"fake-png")
            return {"status": "success", "session_id": resolved_id, "path": str(screenshot_path), "url": active_tab["url"]}

        if action == "browser_list_tabs":
            result_tabs: list[dict[str, Any]] = []
            for index, tab in enumerate(tabs):
                result_tabs.append(
                    {
                        "tab_index": index,
                        "url": tab["url"],
                        "title": tab["title"],
                        "active": index == state["active_tab_index"],
                    }
                )
            return {"session_id": resolved_id, "tabs": result_tabs, "active_tab_index": state["active_tab_index"]}

        if action == "browser_switch_tab":
            tab_index = payload.get("tab_index")
            if not isinstance(tab_index, int) or tab_index < 0 or tab_index >= len(tabs):
                raise BrowserIPCError("tab_not_found", f"Tab index '{tab_index}' does not exist.")
            state["active_tab_index"] = tab_index
            selected_tab = tabs[tab_index]
            return {
                "status": "success",
                "session_id": resolved_id,
                "active_tab_index": tab_index,
                "url": selected_tab["url"],
            }

        if action == "browser_list_interactive_elements":
            filters = payload.get("filters", {})
            if not isinstance(filters, dict):
                filters = {}
            visible_only = filters.get("visible_only", True)
            in_viewport_only = filters.get("in_viewport_only", False)
            text_contains = filters.get("text_contains")
            rows = list(state["interactive_elements"])
            if visible_only:
                rows = [row for row in rows if row.get("visible", False)]
            if in_viewport_only:
                rows = [row for row in rows if row.get("in_viewport", False)]
            if isinstance(text_contains, str) and text_contains:
                needle = text_contains.lower()
                rows = [
                    row for row in rows
                    if needle in str(row.get("text", "")).lower()
                    or needle in str(row.get("aria_label", "")).lower()
                    or needle in str(row.get("placeholder", "")).lower()
                ]
            limit = payload.get("limit", 300)
            if isinstance(limit, int) and limit > 0:
                rows = rows[:limit]
            return {
                "status": "success",
                "session_id": resolved_id,
                "elements": rows,
                "count": len(rows),
            }

        if action == "browser_click_element_by_id":
            element_id = payload.get("element_id")
            target = next((row for row in state["interactive_elements"] if row["element_id"] == element_id), None)
            if target is None:
                raise BrowserIPCError("element_not_found", f"Element '{element_id}' was not found.")
            return {
                "status": "success",
                "session_id": resolved_id,
                "element_id": element_id,
                "selector": target["selector"],
                "url": active_tab["url"],
            }

        if action == "browser_type_into_element":
            element_id = payload.get("element_id")
            target = next((row for row in state["interactive_elements"] if row["element_id"] == element_id), None)
            if target is None:
                raise BrowserIPCError("element_not_found", f"Element '{element_id}' was not found.")
            text = payload.get("text", "")
            state["elements"][target["selector"]] = text
            return {
                "status": "success",
                "session_id": resolved_id,
                "element_id": element_id,
                "selector": target["selector"],
                "url": active_tab["url"],
            }

        if action == "browser_highlight_element":
            element_id = payload.get("element_id")
            target = next((row for row in state["interactive_elements"] if row["element_id"] == element_id), None)
            if target is None:
                raise BrowserIPCError("element_not_found", f"Element '{element_id}' was not found.")
            return {
                "status": "success",
                "session_id": resolved_id,
                "element_id": element_id,
                "selector": target["selector"],
                "url": active_tab["url"],
            }

        raise BrowserIPCError("browser_action_not_supported", f"Unsupported action '{action}'.")

    def _resolve_session_id(self, session_id: str | None) -> str:
        resolved = session_id or self.active_session_id
        if not isinstance(resolved, str) or not resolved:
            raise BrowserIPCError("session_not_available", "No session available.")
        if resolved not in self.sessions:
            raise BrowserIPCError("session_not_available", f"Session '{resolved}' is not available.")
        self.active_session_id = resolved
        return resolved


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _prepare_case_dir(case_name: str) -> Path:
    case_dir = TMP_ROOT / case_name
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir


def _build_runtime(workspace_root: Path, ipc_client: _MockIPCClient | None = None) -> ToolRuntime:
    tool_registry = ToolRegistry()
    contracts_dir = ROOT / "system" / "tools" / "contracts" / "v1"
    for contract_path in sorted(contracts_dir.glob("*.json")):
        tool_registry.register(_load_json(contract_path), source=str(contract_path))

    runtime = ToolRuntime(tool_registry, workspace_root=workspace_root)
    register_phase9_browser_tools(
        runtime,
        workspace_root=workspace_root,
        ipc_client=ipc_client or _MockIPCClient(),
    )
    return runtime


class Phase9BrowserToolsTests(unittest.TestCase):
    def test_alias_resolution_maps_to_canonical_tool(self) -> None:
        case_dir = _prepare_case_dir("alias_resolution")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _build_runtime(workspace)

        self.assertEqual(runtime.resolve_action("browser_click"), "browser_click_element")
        self.assertEqual(runtime.resolve_action("browser_type"), "browser_type_text")
        self.assertEqual(runtime.resolve_action("browser_wait_for"), "browser_wait_for_selector")
        self.assertEqual(runtime.resolve_action("browser_screenshot"), "browser_take_screenshot")

    def test_open_and_close_session(self) -> None:
        case_dir = _prepare_case_dir("open_close")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _build_runtime(workspace)

        opened = runtime.execute("browser_open_session", {"headless": True})
        session_id = opened["session_id"]
        self.assertEqual(opened["status"], "success")
        self.assertTrue(session_id.startswith("session_mock_"))

        closed = runtime.execute("browser_close_session", {"session_id": session_id})
        self.assertEqual(closed["status"], "success")

        with self.assertRaises(ToolExecutionError):
            runtime.execute("browser_close_session", {"session_id": session_id})

    def test_alias_execution_works(self) -> None:
        case_dir = _prepare_case_dir("alias_execution")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _build_runtime(workspace)

        opened = runtime.execute("browser_open_session", {"headless": True})
        session_id = opened["session_id"]
        clicked = runtime.execute("browser_click", {"session_id": session_id, "selector": "#submit"})
        self.assertEqual(clicked["status"], "success")
        self.assertEqual(clicked["session_id"], session_id)

    def test_canonical_execution_works(self) -> None:
        case_dir = _prepare_case_dir("canonical_execution")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _build_runtime(workspace)

        opened = runtime.execute("browser_open_session", {"headless": True})
        session_id = opened["session_id"]
        clicked = runtime.execute("browser_click_element", {"session_id": session_id, "selector": "#submit"})
        self.assertEqual(clicked["status"], "success")
        self.assertEqual(clicked["session_id"], session_id)

    def test_navigation_and_read_text(self) -> None:
        case_dir = _prepare_case_dir("navigate_read")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _build_runtime(workspace)

        opened = runtime.execute("browser_open_session", {"headless": True})
        session_id = opened["session_id"]

        nav = runtime.execute(
            "browser_navigate",
            {"session_id": session_id, "url": "https://example.org/"},
        )
        self.assertEqual(nav["status"], "success")
        self.assertEqual(nav["url"], "https://example.org/")
        self.assertEqual(nav["status_code"], 200)

        text = runtime.execute("browser_read_text", {"session_id": session_id})
        self.assertEqual(text["status"], "success")
        self.assertIn("Body for https://example.org/", text["text"])

    def test_explicit_session_id_takes_precedence(self) -> None:
        case_dir = _prepare_case_dir("explicit_session")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _build_runtime(workspace)

        first = runtime.execute("browser_open_session", {"headless": True})
        second = runtime.execute("browser_open_session", {"headless": True})

        nav_first = runtime.execute(
            "browser_navigate",
            {"session_id": first["session_id"], "url": "https://first.example/"},
        )
        self.assertEqual(nav_first["session_id"], first["session_id"])
        self.assertEqual(nav_first["url"], "https://first.example/")

        nav_second = runtime.execute(
            "browser_navigate",
            {"session_id": second["session_id"], "url": "https://second.example/"},
        )
        self.assertEqual(nav_second["session_id"], second["session_id"])
        self.assertEqual(nav_second["url"], "https://second.example/")

    def test_active_session_id_is_used_when_not_provided(self) -> None:
        case_dir = _prepare_case_dir("active_session")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _build_runtime(workspace)

        opened = runtime.execute("browser_open_session", {"headless": True})
        session_id = opened["session_id"]
        navigated = runtime.execute("browser_navigate", {"url": "https://active.example/"})
        self.assertEqual(navigated["status"], "success")
        self.assertEqual(navigated["session_id"], session_id)
        self.assertEqual(navigated["url"], "https://active.example/")

    def test_error_when_no_session_is_available(self) -> None:
        case_dir = _prepare_case_dir("missing_session")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _build_runtime(workspace)

        with self.assertRaises(ToolExecutionError) as ctx:
            runtime.execute("browser_navigate", {"url": "https://example.org/"})
        self.assertIn("session_not_available", str(ctx.exception))

    def test_screenshot_is_saved_in_workspace(self) -> None:
        case_dir = _prepare_case_dir("screenshot")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _build_runtime(workspace)

        opened = runtime.execute("browser_open_session", {"headless": True})
        screenshot = runtime.execute("browser_take_screenshot", {"path": "shots/screen.png"})
        screenshot_path = Path(screenshot["path"])
        self.assertEqual(screenshot["status"], "success")
        self.assertEqual(screenshot["session_id"], opened["session_id"])
        self.assertTrue(screenshot_path.exists())
        self.assertTrue(str(screenshot_path).startswith(str(workspace.resolve())))

    def test_error_for_non_existing_selector_is_visible(self) -> None:
        case_dir = _prepare_case_dir("missing_selector")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _build_runtime(workspace)

        opened = runtime.execute("browser_open_session", {"headless": True})
        session_id = opened["session_id"]

        with self.assertRaises(ToolExecutionError) as ctx:
            runtime.execute("browser_click", {"session_id": session_id, "selector": "#missing"})
        self.assertIn("selector_not_found", str(ctx.exception))

    def test_error_for_action_keyword_used_as_selector(self) -> None:
        case_dir = _prepare_case_dir("invalid_selector_keyword")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _build_runtime(workspace)

        opened = runtime.execute("browser_open_session", {"headless": True})
        session_id = opened["session_id"]
        with self.assertRaises(ToolExecutionError) as ctx:
            runtime.execute("browser_wait_for_selector", {"session_id": session_id, "selector": "click"})
        self.assertIn("invalid_input", str(ctx.exception))
        self.assertIn("real CSS selector", str(ctx.exception))

    def test_list_tabs_and_switch_tab(self) -> None:
        case_dir = _prepare_case_dir("tabs")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _build_runtime(workspace)

        opened = runtime.execute("browser_open_session", {"headless": True})
        session_id = opened["session_id"]

        tabs = runtime.execute("browser_list_tabs", {"session_id": session_id})
        self.assertGreaterEqual(len(tabs["tabs"]), 2)
        self.assertEqual(tabs["active_tab_index"], 0)

        switched = runtime.execute("browser_switch_tab", {"session_id": session_id, "tab_index": 1})
        self.assertEqual(switched["status"], "success")
        self.assertEqual(switched["active_tab_index"], 1)

        tabs_after = runtime.execute("browser_list_tabs", {"session_id": session_id})
        self.assertEqual(tabs_after["active_tab_index"], 1)

    def test_open_session_without_playwright_reports_clear_error(self) -> None:
        case_dir = _prepare_case_dir("missing_playwright")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)

        failing_client = _MockIPCClient(
            fail_open=BrowserIPCError(
                "playwright_not_installed",
                "Playwright is not installed. Install it before using browser tools.",
            )
        )
        runtime = _build_runtime(workspace, ipc_client=failing_client)
        with self.assertRaises(ToolExecutionError) as ctx:
            runtime.execute("browser_open_session", {"headless": True})
        self.assertIn("playwright_not_installed", str(ctx.exception))

    def test_list_interactive_elements_and_click_by_id(self) -> None:
        case_dir = _prepare_case_dir("list_and_click_by_id")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _build_runtime(workspace)

        opened = runtime.execute("browser_open_session", {"headless": True})
        session_id = opened["session_id"]

        listed = runtime.execute(
            "browser_list_interactive_elements",
            {"session_id": session_id, "filters": {"visible_only": True}},
        )
        self.assertEqual(listed["status"], "success")
        self.assertGreaterEqual(listed["count"], 2)
        element_id = listed["elements"][0]["element_id"]

        clicked = runtime.execute(
            "browser_click_element_by_id",
            {"session_id": session_id, "element_id": element_id},
        )
        self.assertEqual(clicked["status"], "success")
        self.assertEqual(clicked["element_id"], element_id)

    def test_click_by_invalid_id_returns_error(self) -> None:
        case_dir = _prepare_case_dir("click_invalid_id")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        runtime = _build_runtime(workspace)

        opened = runtime.execute("browser_open_session", {"headless": True})
        session_id = opened["session_id"]
        with self.assertRaises(ToolExecutionError) as ctx:
            runtime.execute(
                "browser_click_element_by_id",
                {"session_id": session_id, "element_id": "el_999"},
            )
        self.assertIn("element_not_found", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
