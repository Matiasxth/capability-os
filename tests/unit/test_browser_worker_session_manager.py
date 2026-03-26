from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from system.browser_worker.action_executor import BrowserActionExecutor
from system.browser_worker.session_manager import BrowserWorkerActionError, BrowserWorkerSessionManager

ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tests" / "unit" / ".tmp_runtime" / "browser_worker_session_manager"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


class _FakePlaywrightSession:
    def __init__(self, **kwargs: Any):
        self.tabs = [{"url": "about:blank", "title": "Blank"}]
        self.active_tab_index = 0
        self.elements = {"body": "Fake body", "#name": ""}
        self.interactive_elements = [
            {
                "tag": "button",
                "text": "Submit",
                "aria_label": "",
                "placeholder": "",
                "selector": "#submit",
                "xpath": "/html/body/button[1]",
                "visible": True,
                "enabled": True,
                "bounding_box": {"x": 10.0, "y": 20.0, "width": 120.0, "height": 30.0},
                "in_viewport": True,
                "attributes": {"id": "submit", "class": "", "role": "button", "type": "button"},
            },
            {
                "tag": "a",
                "text": "Open",
                "aria_label": "",
                "placeholder": "",
                "selector": "a:nth-of-type(1)",
                "xpath": "/html/body/a[1]",
                "visible": True,
                "enabled": True,
                "bounding_box": {"x": 12.0, "y": 60.0, "width": 80.0, "height": 24.0},
                "in_viewport": True,
                "attributes": {"id": "", "class": "", "role": "", "type": ""},
            },
        ]
        self.page = _FakePage(self)

    def close(self) -> None:
        return

    def navigate(self, url: str, timeout_ms: int) -> dict[str, Any]:
        self.tabs[self.active_tab_index]["url"] = url
        self.elements["body"] = f"Body for {url}"
        return {"status": "success", "url": url, "status_code": 200}

    def click(self, selector: str, timeout_ms: int) -> dict[str, Any]:
        return {"status": "success", "selector": selector, "url": self.tabs[self.active_tab_index]["url"]}

    def type_text(self, selector: str, text: str, timeout_ms: int) -> dict[str, Any]:
        self.elements[selector] = text
        return {"status": "success", "selector": selector, "url": self.tabs[self.active_tab_index]["url"]}

    def read_text(self, selector: str | None, timeout_ms: int) -> dict[str, Any]:
        target = selector or "body"
        return {"status": "success", "text": self.elements.get(target, ""), "url": self.tabs[self.active_tab_index]["url"]}

    def wait_for_selector(self, selector: str, timeout_ms: int) -> dict[str, Any]:
        return {"status": "success", "selector": selector, "url": self.tabs[self.active_tab_index]["url"]}

    def take_screenshot(self, path: Path, full_page: bool, timeout_ms: int) -> dict[str, Any]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake-png")
        return {"status": "success", "path": str(path), "url": self.tabs[self.active_tab_index]["url"]}

    def list_tabs(self) -> dict[str, Any]:
        return {
            "tabs": [
                {
                    "tab_index": idx,
                    "url": tab["url"],
                    "title": tab["title"],
                    "active": idx == self.active_tab_index,
                }
                for idx, tab in enumerate(self.tabs)
            ],
            "active_tab_index": self.active_tab_index,
        }

    def switch_tab(self, tab_index: int) -> dict[str, Any]:
        if tab_index < 0 or tab_index >= len(self.tabs):
            raise RuntimeError("invalid tab")
        self.active_tab_index = tab_index
        return {"status": "success", "active_tab_index": tab_index, "url": self.tabs[tab_index]["url"]}

    def active_page(self) -> "_FakePage":
        return self.page

    def current_url(self) -> str:
        return self.tabs[self.active_tab_index]["url"]

    def describe_element(self, selector: str, timeout_ms: int) -> dict[str, Any]:
        target = next((row for row in self.interactive_elements if row["selector"] == selector), None)
        if target is None:
            return {"exists": False, "visible": False, "enabled": False, "in_viewport": False, "bounding_box": {}}
        return {
            "exists": True,
            "visible": target["visible"],
            "enabled": target["enabled"],
            "in_viewport": target["in_viewport"],
            "bounding_box": dict(target["bounding_box"]),
        }

    def highlight(self, selector: str, duration_ms: int, timeout_ms: int) -> dict[str, Any]:
        target = next((row for row in self.interactive_elements if row["selector"] == selector), None)
        if target is None:
            raise RuntimeError("selector missing")
        return {"status": "success", "selector": selector, "url": self.current_url()}


class _FakePage:
    def __init__(self, session: _FakePlaywrightSession):
        self._session = session

    def evaluate(self, script: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        _ = script
        _ = payload
        return [dict(row) for row in self._session.interactive_elements]


def _fake_initialize_playwright(self: BrowserWorkerSessionManager) -> None:
    self._playwright_context = object()
    self._playwright_error_cls = Exception
    self._playwright_timeout_cls = Exception
    self._playwright_available = True
    self._playwright_error_message = None


class BrowserWorkerSessionManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case_dir = TMP_ROOT / self._testMethodName
        if self.case_dir.exists():
            shutil.rmtree(self.case_dir)
        self.case_dir.mkdir(parents=True, exist_ok=True)
        self.workspace = self.case_dir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

    def _build_executor(self) -> BrowserActionExecutor:
        init_patcher = patch.object(
            BrowserWorkerSessionManager,
            "_initialize_playwright_runtime",
            _fake_initialize_playwright,
        )
        session_patcher = patch(
            "system.browser_worker.session_manager.PlaywrightSession",
            _FakePlaywrightSession,
        )
        init_patcher.start()
        session_patcher.start()
        self.addCleanup(init_patcher.stop)
        self.addCleanup(session_patcher.stop)
        manager = BrowserWorkerSessionManager(self.workspace)
        self.addCleanup(manager.shutdown)
        return BrowserActionExecutor(manager)

    def test_session_created_navigation_and_screenshot(self) -> None:
        executor = self._build_executor()

        opened = executor.execute(
            action="browser_open_session",
            session_id=None,
            payload={"headless": True},
            metadata={"timeout_ms": 15000},
        )
        session_id = opened["session_id"]
        self.assertTrue(session_id.startswith("session_"))

        navigated = executor.execute(
            action="browser_navigate",
            session_id=session_id,
            payload={"url": "https://example.org/"},
            metadata={"timeout_ms": 15000},
        )
        self.assertEqual(navigated["status"], "success")
        self.assertEqual(navigated["url"], "https://example.org/")

        screenshot = executor.execute(
            action="browser_take_screenshot",
            session_id=session_id,
            payload={"path": "artifacts/screenshots/demo.png", "full_page": False},
            metadata={"timeout_ms": 15000},
        )
        screenshot_path = Path(screenshot["path"])
        self.assertTrue(screenshot_path.exists())
        self.assertTrue(str(screenshot_path).startswith(str(self.workspace.resolve())))

    def test_multiple_sessions(self) -> None:
        executor = self._build_executor()
        first = executor.execute(
            action="browser_open_session",
            session_id=None,
            payload={"headless": True},
            metadata={"timeout_ms": 15000},
        )
        second = executor.execute(
            action="browser_open_session",
            session_id=None,
            payload={"headless": True},
            metadata={"timeout_ms": 15000},
        )
        self.assertNotEqual(first["session_id"], second["session_id"])

    def test_navigate_list_and_click_by_id(self) -> None:
        executor = self._build_executor()
        opened = executor.execute(
            action="browser_open_session",
            session_id=None,
            payload={"headless": True},
            metadata={"timeout_ms": 15000},
        )
        session_id = opened["session_id"]
        executor.execute(
            action="browser_navigate",
            session_id=session_id,
            payload={"url": "https://example.org/"},
            metadata={"timeout_ms": 15000},
        )

        listed = executor.execute(
            action="browser_list_interactive_elements",
            session_id=session_id,
            payload={"filters": {"visible_only": True}},
            metadata={"timeout_ms": 15000},
        )
        self.assertEqual(listed["status"], "success")
        self.assertGreaterEqual(listed["count"], 1)
        element_id = listed["elements"][0]["element_id"]

        clicked = executor.execute(
            action="browser_click_element_by_id",
            session_id=session_id,
            payload={"element_id": element_id},
            metadata={"timeout_ms": 15000},
        )
        self.assertEqual(clicked["status"], "success")
        self.assertEqual(clicked["element_id"], element_id)

    def test_click_by_invalid_id_returns_element_not_found(self) -> None:
        executor = self._build_executor()
        opened = executor.execute(
            action="browser_open_session",
            session_id=None,
            payload={"headless": True},
            metadata={"timeout_ms": 15000},
        )
        session_id = opened["session_id"]

        with self.assertRaises(BrowserWorkerActionError) as ctx:
            executor.execute(
                action="browser_click_element_by_id",
                session_id=session_id,
                payload={"element_id": "el_999"},
                metadata={"timeout_ms": 15000},
            )
        self.assertEqual(ctx.exception.error_code, "element_not_found")

    def test_action_keyword_selector_fails_fast_with_invalid_input(self) -> None:
        executor = self._build_executor()
        opened = executor.execute(
            action="browser_open_session",
            session_id=None,
            payload={"headless": True},
            metadata={"timeout_ms": 15000},
        )
        session_id = opened["session_id"]
        with self.assertRaises(BrowserWorkerActionError) as ctx:
            executor.execute(
                action="browser_wait_for_selector",
                session_id=session_id,
                payload={"selector": "click"},
                metadata={"timeout_ms": 15000},
            )
        self.assertEqual(ctx.exception.error_code, "invalid_input")


if __name__ == "__main__":
    unittest.main()
