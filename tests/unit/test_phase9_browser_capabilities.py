from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from typing import Any

from system.capabilities.registry import CapabilityRegistry
from system.core.capability_engine import CapabilityEngine, CapabilityExecutionError
from system.tools.browser_ipc import BrowserIPCError
from system.tools.registry import ToolRegistry
from system.tools.runtime import (
    ToolRuntime,
    register_phase3_real_tools,
    register_phase9_browser_tools,
)

ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tests" / "unit" / ".tmp_runtime" / "phase9_browser_capabilities"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


class _MockIPCClient:
    def __init__(self):
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
            self.session_counter += 1
            new_session_id = f"session_mock_{self.session_counter}"
            self.sessions[new_session_id] = {
                "url": payload.get("start_url", "about:blank"),
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

        resolved_session_id = self._resolve_session_id(session_id)
        state = self.sessions[resolved_session_id]

        if action == "browser_navigate":
            url = payload.get("url")
            state["url"] = url
            state["elements"]["body"] = f"Body for {url}"
            return {"status": "success", "session_id": resolved_session_id, "url": url, "status_code": 200}

        if action == "browser_click_element":
            selector = payload.get("selector")
            if selector == "#missing":
                raise BrowserIPCError("selector_not_found", "Selector '#missing' was not found.")
            return {"status": "success", "session_id": resolved_session_id, "selector": selector, "url": state["url"]}

        if action == "browser_type_text":
            selector = payload.get("selector")
            text = payload.get("text")
            if selector == "#missing":
                raise BrowserIPCError("selector_not_found", "Selector '#missing' was not found.")
            state["elements"][selector] = text
            return {"status": "success", "session_id": resolved_session_id, "selector": selector, "url": state["url"]}

        if action == "browser_read_text":
            selector = payload.get("selector") or "body"
            if selector == "#missing":
                raise BrowserIPCError("selector_not_found", "Selector '#missing' was not found.")
            return {"status": "success", "session_id": resolved_session_id, "text": state["elements"].get(selector, ""), "url": state["url"]}

        if action == "browser_wait_for_selector":
            selector = payload.get("selector")
            if selector == "#missing":
                raise BrowserIPCError("selector_not_found", "Selector '#missing' was not found.")
            return {"status": "success", "session_id": resolved_session_id, "selector": selector, "url": state["url"]}

        if action == "browser_take_screenshot":
            path = Path(payload.get("path"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fake-png")
            return {"status": "success", "session_id": resolved_session_id, "path": str(path), "url": state["url"]}

        if action == "browser_list_tabs":
            return {
                "session_id": resolved_session_id,
                "tabs": [{"tab_index": 0, "url": state["url"], "title": "Tab 0", "active": True}],
                "active_tab_index": 0,
            }

        if action == "browser_switch_tab":
            tab_index = payload.get("tab_index")
            if tab_index != 0:
                raise BrowserIPCError("tab_not_found", f"Tab index '{tab_index}' does not exist.")
            return {"status": "success", "session_id": resolved_session_id, "active_tab_index": 0, "url": state["url"]}

        if action == "browser_close_session":
            self.sessions.pop(resolved_session_id, None)
            if self.active_session_id == resolved_session_id:
                self.active_session_id = None
            return {"status": "success", "session_id": resolved_session_id}

        if action == "browser_list_interactive_elements":
            rows = list(state["interactive_elements"])
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
                        row for row in rows
                        if needle in str(row.get("text", "")).lower()
                        or needle in str(row.get("aria_label", "")).lower()
                        or needle in str(row.get("placeholder", "")).lower()
                    ]
            return {"status": "success", "session_id": resolved_session_id, "elements": rows, "count": len(rows)}

        if action == "browser_click_element_by_id":
            element_id = payload.get("element_id")
            target = next((row for row in state["interactive_elements"] if row["element_id"] == element_id), None)
            if target is None:
                raise BrowserIPCError("element_not_found", f"Element '{element_id}' was not found.")
            return {
                "status": "success",
                "session_id": resolved_session_id,
                "element_id": element_id,
                "selector": target["selector"],
                "url": state["url"],
            }

        if action == "browser_type_into_element":
            element_id = payload.get("element_id")
            target = next((row for row in state["interactive_elements"] if row["element_id"] == element_id), None)
            if target is None:
                raise BrowserIPCError("element_not_found", f"Element '{element_id}' was not found.")
            state["elements"][target["selector"]] = payload.get("text", "")
            return {
                "status": "success",
                "session_id": resolved_session_id,
                "element_id": element_id,
                "selector": target["selector"],
                "url": state["url"],
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


def _build_engine(workspace_root: Path) -> tuple[CapabilityEngine, CapabilityRegistry]:
    capability_registry = CapabilityRegistry()
    for contract_path in sorted((ROOT / "system" / "capabilities" / "contracts" / "v1").glob("*.json")):
        capability_registry.register(_load_json(contract_path), source=str(contract_path))

    tool_registry = ToolRegistry()
    for contract_path in sorted((ROOT / "system" / "tools" / "contracts" / "v1").glob("*.json")):
        tool_registry.register(_load_json(contract_path), source=str(contract_path))

    tool_runtime = ToolRuntime(tool_registry, workspace_root=workspace_root)
    register_phase3_real_tools(tool_runtime, workspace_root)
    register_phase9_browser_tools(tool_runtime, workspace_root, ipc_client=_MockIPCClient())
    return CapabilityEngine(capability_registry, tool_runtime), capability_registry


class Phase9BrowserCapabilitiesTests(unittest.TestCase):
    def test_contracts_validate(self) -> None:
        registry = CapabilityRegistry()
        for capability_id in (
            "open_browser",
            "navigate_web",
            "read_web_page",
            "interact_with_page",
            "browser_list_interactive_elements",
            "browser_click_element_by_id",
            "browser_type_into_element",
            "browser_highlight_element",
        ):
            contract = _load_json(ROOT / "system" / "capabilities" / "contracts" / "v1" / f"{capability_id}.json")
            validated_id = registry.validate_contract(contract, source=f"phase9_{capability_id}")
            self.assertEqual(validated_id, capability_id)

    def test_open_navigate_read_e2e(self) -> None:
        case_dir = _prepare_case_dir("open_navigate_read")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        engine, caps = _build_engine(workspace)

        open_browser_contract = caps.get("open_browser")
        self.assertIsNotNone(open_browser_contract)
        opened = engine.execute(open_browser_contract, {"headless": True})
        session_id = opened["final_output"]["session_id"]
        self.assertTrue(session_id.startswith("session_mock_"))

        navigate_web_contract = caps.get("navigate_web")
        self.assertIsNotNone(navigate_web_contract)
        navigated = engine.execute(
            navigate_web_contract,
            {"session_id": session_id, "url": "https://example.com/"},
        )
        self.assertEqual(navigated["status"], "success")
        self.assertEqual(navigated["final_output"]["status_code"], 200)

        read_web_page_contract = caps.get("read_web_page")
        self.assertIsNotNone(read_web_page_contract)
        read = engine.execute(read_web_page_contract, {"session_id": session_id})
        self.assertEqual(read["status"], "success")
        self.assertIn("Body for https://example.com/", read["final_output"]["text"])

    def test_interact_with_page_e2e(self) -> None:
        case_dir = _prepare_case_dir("interact_success")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        engine, caps = _build_engine(workspace)

        open_browser_contract = caps.get("open_browser")
        self.assertIsNotNone(open_browser_contract)
        opened = engine.execute(open_browser_contract, {"headless": True})
        session_id = opened["final_output"]["session_id"]

        interact_contract = caps.get("interact_with_page")
        self.assertIsNotNone(interact_contract)
        interact = engine.execute(
            interact_contract,
            {
                "session_id": session_id,
                "selector": "#name",
                "text": "Alice",
            },
        )
        self.assertEqual(interact["status"], "success")
        self.assertEqual(interact["final_output"]["status"], "success")
        self.assertEqual(interact["final_output"]["selector"], "#name")

    def test_interact_with_page_selector_error_and_logs(self) -> None:
        case_dir = _prepare_case_dir("interact_error")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        engine, caps = _build_engine(workspace)

        open_browser_contract = caps.get("open_browser")
        self.assertIsNotNone(open_browser_contract)
        opened = engine.execute(open_browser_contract, {"headless": True})
        session_id = opened["final_output"]["session_id"]

        interact_contract = caps.get("interact_with_page")
        self.assertIsNotNone(interact_contract)
        with self.assertRaises(CapabilityExecutionError) as ctx:
            engine.execute(
                interact_contract,
                {
                    "session_id": session_id,
                    "selector": "#missing",
                    "text": "x",
                },
            )

        runtime = ctx.exception.runtime_model
        events = [entry["event"] for entry in runtime["logs"]]
        self.assertEqual(runtime["status"], "error")
        self.assertEqual(ctx.exception.error_code, "tool_execution_error")
        self.assertIn("step_failed", events)
        self.assertEqual(events[-1], "execution_finished")
        self.assertEqual(runtime["failed_step"], "wait_for_selector")

    def test_navigate_list_click_with_element_ids(self) -> None:
        case_dir = _prepare_case_dir("navigate_list_click_by_id")
        workspace = case_dir / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        engine, caps = _build_engine(workspace)

        open_contract = caps.get("open_browser")
        navigate_contract = caps.get("navigate_web")
        list_contract = caps.get("browser_list_interactive_elements")
        click_contract = caps.get("browser_click_element_by_id")
        self.assertIsNotNone(open_contract)
        self.assertIsNotNone(navigate_contract)
        self.assertIsNotNone(list_contract)
        self.assertIsNotNone(click_contract)

        opened = engine.execute(open_contract, {"headless": True})
        session_id = opened["final_output"]["session_id"]
        engine.execute(navigate_contract, {"session_id": session_id, "url": "https://example.com/"})

        listed = engine.execute(
            list_contract,
            {"session_id": session_id, "filters": {"visible_only": True}},
        )
        self.assertEqual(listed["status"], "success")
        self.assertGreaterEqual(listed["final_output"]["count"], 1)
        first_id = listed["final_output"]["elements"][0]["element_id"]

        clicked = engine.execute(
            click_contract,
            {"session_id": session_id, "element_id": first_id},
        )
        self.assertEqual(clicked["status"], "success")
        self.assertEqual(clicked["final_output"]["element_id"], first_id)


if __name__ == "__main__":
    unittest.main()
