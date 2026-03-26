from __future__ import annotations

import json
import re
import shutil
import unittest
from pathlib import Path
from typing import Any

from system.capabilities.implementations import Phase10WhatsAppCapabilityExecutor
from system.capabilities.registry import CapabilityRegistry
from system.core.ui_bridge.api_server import CapabilityOSUIBridgeService
from system.shared.schema_validation import load_schema, validate_instance
from system.tools.runtime import ToolExecutionError

ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tests" / "unit" / ".tmp_runtime" / "phase10_whatsapp"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


def _tool_error(error_code: str, error_message: str) -> ToolExecutionError:
    payload = json.dumps({"error_code": error_code, "error_message": error_message}, ensure_ascii=True)
    return ToolExecutionError(f"mock_browser_error: {payload}")


class _MockBrowserLayer:
    def __init__(self):
        self.session_counter = 0
        self.active_session_id: str | None = None
        self.sessions: dict[str, dict[str, Any]] = {}
        self.login_mode = "qr_visible"
        self.visible_chats = ["Alice", "Project Team", "Bob"]
        self.selected_chat = "Alice"
        self.messages_by_chat = {
            "Alice": ["Hola Alice", "Mensaje visible 2", "Mensaje visible 3"],
            "Project Team": ["Build green", "Tests passed"]
        }
        self.search_query = ""
        self.composer_buffer = ""
        self.sent_messages: list[dict[str, Any]] = []
        self.send_button_available = True
        self.interactive_elements: list[dict[str, Any]] = [
            {
                "element_id": "el_search",
                "type": "input",
                "text": "",
                "aria_label": "Search or start new chat",
                "placeholder": "Search or start new chat",
                "selector": "#search_input",
                "xpath": "/html/body/div[1]/div[1]",
                "visible": True,
                "enabled": True,
                "bounding_box": {"x": 12, "y": 16, "width": 220, "height": 34},
                "in_viewport": True,
                "tag": "div",
                "attributes": {"id": "", "class": "", "role": "textbox", "type": ""},
            },
            {
                "element_id": "el_composer",
                "type": "input",
                "text": "",
                "aria_label": "Type a message",
                "placeholder": "Type a message",
                "selector": "#composer",
                "xpath": "/html/body/div[1]/div[2]",
                "visible": True,
                "enabled": True,
                "bounding_box": {"x": 10, "y": 100, "width": 300, "height": 30},
                "in_viewport": True,
                "tag": "div",
                "attributes": {"id": "", "class": "", "role": "textbox", "type": ""},
            },
        ]

    def open_session(self, params: dict[str, Any]) -> dict[str, Any]:
        self.session_counter += 1
        session_id = f"session_mock_{self.session_counter}"
        start_url = params.get("start_url")
        url = start_url if isinstance(start_url, str) and start_url else "about:blank"
        self.sessions[session_id] = {"url": url}
        self.active_session_id = session_id
        return {"status": "success", "session_id": session_id, "url": url}

    def navigate(self, params: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        url = params.get("url")
        if not isinstance(url, str) or not url:
            raise _tool_error("invalid_input", "url is required")
        self.sessions[session_id]["url"] = url
        return {"status": "success", "session_id": session_id, "url": url, "status_code": 200}

    def wait_for_selector(self, params: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        selector = params.get("selector")
        if not isinstance(selector, str) or not selector:
            raise _tool_error("invalid_input", "selector is required")

        visible = False
        if selector == "#auth" and self.login_mode == "authenticated":
            visible = True
        elif selector == "#qr" and self.login_mode == "qr_visible":
            visible = True
        elif selector in {"#search_input", "#chat_results", "#chat_list", "#message_list", "#composer", "#send_button"}:
            visible = selector != "#send_button" or self.send_button_available
        elif self._extract_chat_name(selector) in self.visible_chats:
            visible = True

        if not visible:
            raise _tool_error("selector_not_found", f"selector '{selector}' not found")
        return {
            "status": "success",
            "session_id": session_id,
            "selector": selector,
            "url": self.sessions[session_id]["url"],
        }

    def click(self, params: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        selector = params.get("selector")
        if not isinstance(selector, str) or not selector:
            raise _tool_error("invalid_input", "selector is required")

        chat_name = self._extract_chat_name(selector)
        if chat_name is not None:
            if chat_name not in self.visible_chats:
                raise _tool_error("selector_not_found", f"chat '{chat_name}' not found")
            self.selected_chat = chat_name
            return {"status": "success", "session_id": session_id, "selector": selector, "url": self.sessions[session_id]["url"]}

        if selector == "#send_button":
            if not self.send_button_available:
                raise _tool_error("selector_not_found", "send button not available")
            if self.selected_chat is None:
                raise _tool_error("selector_not_found", "no active chat")
            message = self.composer_buffer.strip()
            if not message:
                raise _tool_error("invalid_input", "empty message")
            self.messages_by_chat.setdefault(self.selected_chat, []).append(message)
            self.sent_messages.append({"chat": self.selected_chat, "message": message, "session_id": session_id})
            self.composer_buffer = ""
            return {"status": "success", "session_id": session_id, "selector": selector, "url": self.sessions[session_id]["url"]}

        if selector in {"#search_input", "#composer"}:
            return {
                "status": "success",
                "session_id": session_id,
                "selector": selector,
                "url": self.sessions[session_id]["url"],
            }

        raise _tool_error("selector_not_found", f"selector '{selector}' not found")

    def type_text(self, params: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        selector = params.get("selector")
        text = params.get("text")
        if not isinstance(selector, str) or not selector:
            raise _tool_error("invalid_input", "selector is required")
        if not isinstance(text, str):
            raise _tool_error("invalid_input", "text is required")
        if selector == "#search_input":
            self.search_query = text
        if selector == "#composer":
            self.composer_buffer = text
        return {"status": "success", "session_id": session_id, "selector": selector, "url": self.sessions[session_id]["url"]}

    def read_text(self, params: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        selector = params.get("selector")
        if not isinstance(selector, str) or not selector:
            selector = "body"

        if selector == "body":
            if self.login_mode == "authenticated":
                text = "Search or start new chat\nChat list"
            elif self.login_mode == "qr_visible":
                text = "Scan the QR code to log in"
            else:
                text = "Loading WhatsApp..."
        elif selector == "#chat_results":
            lowered = self.search_query.lower()
            matches = [item for item in self.visible_chats if lowered in item.lower()]
            text = "\n".join(matches)
        elif selector == "#chat_list":
            text = "\n".join(self.visible_chats)
        elif selector == "#message_list":
            current_chat = self.selected_chat or (self.visible_chats[0] if self.visible_chats else None)
            text = "\n".join(self.messages_by_chat.get(current_chat or "", []))
        else:
            text = ""

        return {
            "status": "success",
            "session_id": session_id,
            "text": text,
            "url": self.sessions[session_id]["url"],
        }

    def list_interactive_elements(self, params: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        filters = params.get("filters", {})
        if not isinstance(filters, dict):
            filters = {}
        rows = list(self.interactive_elements)
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
            "session_id": session_id,
            "elements": rows,
            "count": len(rows),
        }

    def click_by_id(self, params: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        element_id = params.get("element_id")
        target = next((row for row in self.interactive_elements if row["element_id"] == element_id), None)
        if target is None:
            raise _tool_error("element_not_found", f"element '{element_id}' not found")
        return self.click({"session_id": session_id, "selector": target["selector"]})

    def type_into_element(self, params: dict[str, Any]) -> dict[str, Any]:
        session_id = self._resolve_session_id(params)
        element_id = params.get("element_id")
        text = params.get("text")
        target = next((row for row in self.interactive_elements if row["element_id"] == element_id), None)
        if target is None:
            raise _tool_error("element_not_found", f"element '{element_id}' not found")
        return self.type_text({"session_id": session_id, "selector": target["selector"], "text": text})

    def _resolve_session_id(self, params: dict[str, Any]) -> str:
        session_id = params.get("session_id")
        if isinstance(session_id, str) and session_id:
            if session_id not in self.sessions:
                raise _tool_error("session_not_found", f"session '{session_id}' not found")
            self.active_session_id = session_id
            return session_id
        if self.active_session_id is None:
            raise _tool_error("session_not_available", "no active session")
        return self.active_session_id

    @staticmethod
    def _extract_chat_name(selector: str) -> str | None:
        single = re.search(r"\[data-chat='([^']+)'\]", selector)
        if single is not None:
            return single.group(1)
        double = re.search(r'\[data-chat="([^"]+)"\]', selector)
        if double is not None:
            return double.group(1)
        return None


class Phase10WhatsAppConnectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case_dir = TMP_ROOT / self._testMethodName
        if self.case_dir.exists():
            shutil.rmtree(self.case_dir)
        self.case_dir.mkdir(parents=True, exist_ok=True)
        self.workspace = self.case_dir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.selectors_path = self.case_dir / "selectors.json"
        self._write_selectors_config(self.selectors_path)

        self.service = CapabilityOSUIBridgeService(workspace_root=self.workspace)
        self.browser = _MockBrowserLayer()
        self._install_browser_mocks()
        self.service.phase10_whatsapp_executor = Phase10WhatsAppCapabilityExecutor(
            self.service.capability_registry,
            self.service.tool_runtime,
            self.selectors_path,
        )
        validated = self.service.handle("POST", "/integrations/whatsapp_web_connector/validate", {})
        if validated.status_code == 200 and validated.payload.get("status") == "success":
            self.service.handle("POST", "/integrations/whatsapp_web_connector/enable", {})

    def _write_selectors_config(self, path: Path) -> None:
        config = {
            "base_url": "https://web.whatsapp.com/",
            "default_timeout_ms": 2000,
            "default_poll_interval_ms": 10,
            "login": {
                "authenticated_selectors": ["#auth"],
                "qr_visible_selectors": ["#qr"]
            },
            "chat": {
                "search_input_selectors": ["#search_input"],
                "results_list_selectors": ["#chat_results"],
                "chat_row_selector_template": "[data-chat=\"{chat_name}\"]",
                "visible_list_selectors": ["#chat_list"]
            },
            "message": {
                "message_list_selectors": ["#message_list"],
                "composer_input_selectors": ["#composer"],
                "send_button_selectors": ["#send_button"]
            }
        }
        path.write_text(json.dumps(config, indent=2), encoding="utf-8-sig")

    def _install_browser_mocks(self) -> None:
        runtime = self.service.tool_runtime
        runtime.register_handler("browser_open_session", lambda params, contract, ctx: self.browser.open_session(params))
        runtime.register_handler("browser_navigate", lambda params, contract, ctx: self.browser.navigate(params))
        runtime.register_handler("browser_wait_for_selector", lambda params, contract, ctx: self.browser.wait_for_selector(params))
        runtime.register_handler("browser_click_element", lambda params, contract, ctx: self.browser.click(params))
        runtime.register_handler("browser_type_text", lambda params, contract, ctx: self.browser.type_text(params))
        runtime.register_handler("browser_read_text", lambda params, contract, ctx: self.browser.read_text(params))
        runtime.register_handler(
            "browser_list_interactive_elements",
            lambda params, contract, ctx: self.browser.list_interactive_elements(params),
        )
        runtime.register_handler("browser_click_element_by_id", lambda params, contract, ctx: self.browser.click_by_id(params))
        runtime.register_handler("browser_type_into_element", lambda params, contract, ctx: self.browser.type_into_element(params))

    def _execute(self, capability_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
        response = self.service.handle("POST", "/execute", {"capability_id": capability_id, "inputs": inputs})
        self.assertEqual(response.status_code, 200)
        return response.payload

    def test_open_whatsapp_web_opens_session_and_detects_qr(self) -> None:
        self.browser.login_mode = "qr_visible"
        payload = self._execute("open_whatsapp_web", {})
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["final_output"]["login_state"], "qr_visible")
        self.assertTrue(payload["final_output"]["session_id"].startswith("session_mock_"))

    def test_wait_for_whatsapp_login_detects_all_expected_states(self) -> None:
        opened = self._execute("open_whatsapp_web", {})
        session_id = opened["final_output"]["session_id"]

        self.browser.login_mode = "qr_visible"
        qr = self._execute("wait_for_whatsapp_login", {"session_id": session_id, "timeout_ms": 50, "poll_interval_ms": 10})
        self.assertEqual(qr["status"], "success")
        self.assertEqual(qr["final_output"]["login_state"], "qr_visible")

        self.browser.login_mode = "authenticated"
        authenticated = self._execute(
            "wait_for_whatsapp_login",
            {"session_id": session_id, "timeout_ms": 50, "poll_interval_ms": 10},
        )
        self.assertEqual(authenticated["final_output"]["login_state"], "authenticated")

        self.browser.login_mode = "none"
        timeout = self._execute("wait_for_whatsapp_login", {"session_id": session_id, "timeout_ms": 30, "poll_interval_ms": 10})
        self.assertEqual(timeout["final_output"]["login_state"], "timeout")

    def test_search_whatsapp_chat(self) -> None:
        self.browser.login_mode = "authenticated"
        opened = self._execute("open_whatsapp_web", {})
        session_id = opened["final_output"]["session_id"]

        payload = self._execute(
            "search_whatsapp_chat",
            {"session_id": session_id, "chat_name": "Alice"},
        )
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["final_output"]["status"], "success")
        self.assertTrue(payload["final_output"]["selected"])
        self.assertIn("Alice", payload["final_output"]["matches"])

    def test_search_whatsapp_chat_falls_back_to_next_selector(self) -> None:
        self.browser.login_mode = "authenticated"
        opened = self._execute("open_whatsapp_web", {})
        session_id = opened["final_output"]["session_id"]

        connector = self.service.phase10_whatsapp_executor.connector
        connector.chat_search_selectors = ["#missing_search_box", "#search_input"]

        payload = self._execute(
            "search_whatsapp_chat",
            {"session_id": session_id, "chat_name": "Alice"},
        )
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["final_output"]["status"], "success")
        self.assertEqual(payload["final_output"]["search_resolution"]["mode"], "selector")
        self.assertEqual(payload["final_output"]["search_resolution"]["selector"], "#search_input")

    def test_search_whatsapp_chat_uses_dom_fallback_when_selectors_fail(self) -> None:
        self.browser.login_mode = "authenticated"
        opened = self._execute("open_whatsapp_web", {})
        session_id = opened["final_output"]["session_id"]

        connector = self.service.phase10_whatsapp_executor.connector
        connector.chat_search_selectors = ["#missing_search_box_a", "#missing_search_box_b"]

        payload = self._execute(
            "search_whatsapp_chat",
            {"session_id": session_id, "chat_name": "Alice"},
        )
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["final_output"]["status"], "success")
        self.assertEqual(payload["final_output"]["search_resolution"]["mode"], "element_id")
        self.assertEqual(payload["final_output"]["search_resolution"]["element_id"], "el_search")

    def test_read_whatsapp_messages_visible_only(self) -> None:
        self.browser.login_mode = "authenticated"
        opened = self._execute("open_whatsapp_web", {})
        session_id = opened["final_output"]["session_id"]
        self.browser.selected_chat = "Alice"

        payload = self._execute(
            "read_whatsapp_messages",
            {"session_id": session_id, "max_messages": 2},
        )
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["final_output"]["scope"], "visible_only")
        self.assertEqual(payload["final_output"]["message_count"], 2)
        messages = payload["final_output"]["messages"]
        self.assertEqual(len(messages), 2)
        self.assertIn("Mensaje visible", messages[0]["text"] + messages[1]["text"])

    def test_send_whatsapp_message_and_error_handling(self) -> None:
        self.browser.login_mode = "authenticated"
        opened = self._execute("open_whatsapp_web", {})
        session_id = opened["final_output"]["session_id"]
        self.browser.selected_chat = "Alice"

        success = self._execute(
            "send_whatsapp_message",
            {"session_id": session_id, "message": "Hola desde test"},
        )
        self.assertEqual(success["status"], "success")
        self.assertEqual(success["final_output"]["confirmation"], "sent")
        self.assertTrue(any(item["message"] == "Hola desde test" for item in self.browser.sent_messages))

        self.browser.send_button_available = False
        failure = self._execute(
            "send_whatsapp_message",
            {"session_id": session_id, "message": "Debe fallar"},
        )
        self.assertEqual(failure["status"], "error")
        self.assertEqual(failure["error_code"], "send_button_not_found")

    def test_list_whatsapp_visible_chats(self) -> None:
        self.browser.login_mode = "authenticated"
        opened = self._execute("open_whatsapp_web", {})
        session_id = opened["final_output"]["session_id"]

        payload = self._execute("list_whatsapp_visible_chats", {"session_id": session_id, "max_chats": 2})
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["final_output"]["chat_count"], 2)
        chats = payload["final_output"]["chats"]
        self.assertEqual(chats[0]["name"], "Alice")

    def test_manifest_and_capability_contracts_validate(self) -> None:
        schema = load_schema(ROOT / "system" / "integrations" / "contracts" / "integration_manifest.schema.json")
        manifest = json.loads(
            (ROOT / "system" / "integrations" / "installed" / "whatsapp_web_connector" / "manifest.json").read_text(
                encoding="utf-8-sig"
            )
        )
        validate_instance(manifest, schema, context="whatsapp manifest")

        registry = CapabilityRegistry()
        for capability_id in (
            "open_whatsapp_web",
            "wait_for_whatsapp_login",
            "search_whatsapp_chat",
            "read_whatsapp_messages",
            "send_whatsapp_message",
            "list_whatsapp_visible_chats",
        ):
            contract_path = ROOT / "system" / "capabilities" / "contracts" / "v1" / f"{capability_id}.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
            validated_id = registry.validate_contract(contract, source=str(contract_path))
            self.assertEqual(validated_id, capability_id)


if __name__ == "__main__":
    unittest.main()
