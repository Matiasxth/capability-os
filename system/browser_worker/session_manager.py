from __future__ import annotations

import uuid
from pathlib import Path
from threading import RLock
from typing import Any


class BrowserWorkerActionError(RuntimeError):
    def __init__(self, error_code: str, error_message: str, details: dict[str, Any] | None = None):
        super().__init__(error_message)
        self.error_code = error_code
        self.error_message = error_message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "error_code": self.error_code,
            "error_message": self.error_message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


class PlaywrightSession:
    def __init__(
        self,
        *,
        playwright_context: Any,
        playwright_error_cls: type[Exception],
        playwright_timeout_cls: type[Exception],
        headless: bool,
    ):
        self._playwright_error_cls = playwright_error_cls
        self._playwright_timeout_cls = playwright_timeout_cls
        try:
            self._browser = playwright_context.chromium.launch(headless=headless)
            self._context = self._browser.new_context()
            self._context.new_page()
            self._active_tab_index = 0
        except Exception as exc:
            raise BrowserWorkerActionError(
                "browser_launch_failed",
                f"Failed to launch browser session: {exc}",
            ) from exc

    def close(self) -> None:
        try:
            self._context.close()
        finally:
            self._browser.close()

    def navigate(self, url: str, timeout_ms: int) -> dict[str, Any]:
        page = self._active_page()
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            return {
                "status": "success",
                "url": page.url,
                "status_code": int(response.status) if response is not None else 0,
            }
        except self._playwright_timeout_cls as exc:
            raise BrowserWorkerActionError(
                "navigation_failed",
                f"Navigation timed out after {timeout_ms} ms for url '{url}'.",
                {"timeout_ms": timeout_ms, "url": url},
            ) from exc
        except self._playwright_error_cls as exc:
            raise BrowserWorkerActionError(
                "navigation_failed",
                f"Navigation failed: {exc}",
                {"url": url},
            ) from exc

    def click(self, selector: str, timeout_ms: int) -> dict[str, Any]:
        page = self._active_page()
        try:
            page.click(selector, timeout=timeout_ms)
            return {"status": "success", "selector": selector, "url": page.url}
        except self._playwright_timeout_cls as exc:
            raise BrowserWorkerActionError(
                "selector_not_found",
                f"Selector '{selector}' not found within {timeout_ms} ms.",
                {"selector": selector, "timeout_ms": timeout_ms},
            ) from exc
        except self._playwright_error_cls as exc:
            raise BrowserWorkerActionError(
                "click_failed",
                f"Click failed for selector '{selector}': {exc}",
                {"selector": selector},
            ) from exc

    def type_text(self, selector: str, text: str, timeout_ms: int) -> dict[str, Any]:
        page = self._active_page()
        try:
            page.fill(selector, text, timeout=timeout_ms)
            return {"status": "success", "selector": selector, "url": page.url}
        except self._playwright_timeout_cls as exc:
            raise BrowserWorkerActionError(
                "selector_not_found",
                f"Selector '{selector}' not found within {timeout_ms} ms.",
                {"selector": selector, "timeout_ms": timeout_ms},
            ) from exc
        except self._playwright_error_cls as exc:
            raise BrowserWorkerActionError(
                "type_failed",
                f"Typing failed for selector '{selector}': {exc}",
                {"selector": selector},
            ) from exc

    def read_text(self, selector: str | None, timeout_ms: int) -> dict[str, Any]:
        page = self._active_page()
        effective_selector = selector or "body"
        try:
            text = page.inner_text(effective_selector, timeout=timeout_ms)
            return {"status": "success", "text": text, "url": page.url}
        except self._playwright_timeout_cls as exc:
            raise BrowserWorkerActionError(
                "selector_not_found",
                f"Selector '{effective_selector}' not found within {timeout_ms} ms.",
                {"selector": effective_selector, "timeout_ms": timeout_ms},
            ) from exc
        except self._playwright_error_cls as exc:
            raise BrowserWorkerActionError(
                "read_text_failed",
                f"Read text failed for selector '{effective_selector}': {exc}",
                {"selector": effective_selector},
            ) from exc

    def wait_for_selector(self, selector: str, timeout_ms: int) -> dict[str, Any]:
        page = self._active_page()
        try:
            page.wait_for_selector(selector, timeout=timeout_ms)
            return {"status": "success", "selector": selector, "url": page.url}
        except self._playwright_timeout_cls as exc:
            raise BrowserWorkerActionError(
                "selector_not_found",
                f"Selector '{selector}' not found within {timeout_ms} ms.",
                {"selector": selector, "timeout_ms": timeout_ms},
            ) from exc
        except self._playwright_error_cls as exc:
            raise BrowserWorkerActionError(
                "wait_failed",
                f"Wait failed for selector '{selector}': {exc}",
                {"selector": selector},
            ) from exc

    def take_screenshot(self, path: Path, full_page: bool, timeout_ms: int) -> dict[str, Any]:
        page = self._active_page()
        try:
            page.screenshot(path=str(path), full_page=full_page, timeout=timeout_ms)
            return {"status": "success", "path": str(path), "url": page.url}
        except self._playwright_timeout_cls as exc:
            raise BrowserWorkerActionError(
                "screenshot_failed",
                f"Screenshot timed out after {timeout_ms} ms.",
                {"timeout_ms": timeout_ms, "path": str(path)},
            ) from exc
        except self._playwright_error_cls as exc:
            raise BrowserWorkerActionError(
                "screenshot_failed",
                f"Screenshot failed: {exc}",
                {"path": str(path)},
            ) from exc

    def list_tabs(self) -> dict[str, Any]:
        pages = self._pages()
        tabs: list[dict[str, Any]] = []
        for index, page in enumerate(pages):
            title = ""
            try:
                title = page.title()
            except Exception:
                title = ""
            tabs.append(
                {
                    "tab_index": index,
                    "url": page.url,
                    "title": title,
                    "active": index == self._active_tab_index,
                }
            )
        return {"tabs": tabs, "active_tab_index": self._active_tab_index}

    def switch_tab(self, tab_index: int) -> dict[str, Any]:
        pages = self._pages()
        if tab_index < 0 or tab_index >= len(pages):
            raise BrowserWorkerActionError(
                "tab_not_found",
                f"Tab index '{tab_index}' does not exist.",
                {"available_tabs": len(pages)},
            )
        self._active_tab_index = tab_index
        page = pages[tab_index]
        page.bring_to_front()
        return {"status": "success", "active_tab_index": tab_index, "url": page.url}

    def active_page(self) -> Any:
        return self._active_page()

    def current_url(self) -> str:
        return self._active_page().url

    def describe_element(self, selector: str, timeout_ms: int) -> dict[str, Any]:
        page = self._active_page()
        locator = page.locator(selector).first
        try:
            count = locator.count()
        except self._playwright_error_cls as exc:
            raise BrowserWorkerActionError(
                "element_not_found",
                f"Could not resolve selector '{selector}': {exc}",
                {"selector": selector},
            ) from exc

        if count <= 0:
            return {
                "exists": False,
                "visible": False,
                "enabled": False,
                "in_viewport": False,
                "bounding_box": {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0},
                "url": page.url,
            }

        try:
            visible = bool(locator.is_visible(timeout=timeout_ms))
        except self._playwright_timeout_cls:
            visible = False
        except self._playwright_error_cls:
            visible = False

        try:
            enabled = bool(locator.is_enabled(timeout=timeout_ms))
        except self._playwright_timeout_cls:
            enabled = False
        except self._playwright_error_cls:
            enabled = False

        try:
            box = locator.bounding_box()
        except self._playwright_error_cls:
            box = None
        bounding_box = {
            "x": float(box.get("x", 0.0)) if isinstance(box, dict) else 0.0,
            "y": float(box.get("y", 0.0)) if isinstance(box, dict) else 0.0,
            "width": float(box.get("width", 0.0)) if isinstance(box, dict) else 0.0,
            "height": float(box.get("height", 0.0)) if isinstance(box, dict) else 0.0,
        }

        viewport = page.viewport_size or {}
        in_viewport = _compute_in_viewport(bounding_box, viewport)
        return {
            "exists": True,
            "visible": visible,
            "enabled": enabled,
            "in_viewport": in_viewport,
            "bounding_box": bounding_box,
            "url": page.url,
        }

    def highlight(self, selector: str, duration_ms: int, timeout_ms: int) -> dict[str, Any]:
        page = self._active_page()
        script = """
({ selector, durationMs }) => {
  const element = document.querySelector(selector);
  if (!element) {
    return { found: false };
  }
  const previousOutline = element.style.outline;
  const previousTransition = element.style.transition;
  element.style.outline = "2px solid #ff4d4f";
  element.style.transition = "outline 120ms ease-in-out";
  setTimeout(() => {
    element.style.outline = previousOutline;
    element.style.transition = previousTransition;
  }, durationMs);
  return { found: true };
}
"""
        try:
            result = page.evaluate(script, {"selector": selector, "durationMs": duration_ms})
            if not isinstance(result, dict) or not result.get("found", False):
                raise BrowserWorkerActionError(
                    "element_not_found",
                    f"Selector '{selector}' was not found for highlight.",
                    {"selector": selector},
                )
            return {"status": "success", "selector": selector, "url": page.url}
        except BrowserWorkerActionError:
            raise
        except self._playwright_timeout_cls as exc:
            raise BrowserWorkerActionError(
                "element_not_interactable",
                f"Highlight operation timed out for selector '{selector}'.",
                {"selector": selector, "timeout_ms": timeout_ms},
            ) from exc
        except self._playwright_error_cls as exc:
            raise BrowserWorkerActionError(
                "element_not_interactable",
                f"Highlight operation failed for selector '{selector}': {exc}",
                {"selector": selector},
            ) from exc

    def _pages(self) -> list[Any]:
        pages = list(self._context.pages)
        if not pages:
            pages = [self._context.new_page()]
        if self._active_tab_index >= len(pages):
            self._active_tab_index = len(pages) - 1
        return pages

    def _active_page(self) -> Any:
        pages = self._pages()
        return pages[self._active_tab_index]


class BrowserWorkerSessionManager:
    def __init__(self, workspace_root: str | Path):
        self.workspace_root = Path(workspace_root).resolve()
        self._lock = RLock()
        self._sessions: dict[str, PlaywrightSession] = {}
        self._active_session_id: str | None = None

        self._playwright_context: Any | None = None
        self._playwright_error_cls: type[Exception] | None = None
        self._playwright_timeout_cls: type[Exception] | None = None
        self._playwright_available = False
        self._playwright_error_message: str | None = None
        self._initialize_playwright_runtime()

    @property
    def active_session_id(self) -> str | None:
        with self._lock:
            return self._active_session_id

    @property
    def session_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    @property
    def playwright_available(self) -> bool:
        return self._playwright_available

    def open_session(self, *, headless: bool) -> str:
        self._ensure_playwright_available()
        if not isinstance(headless, bool):
            raise BrowserWorkerActionError("invalid_input", "Field 'headless' must be a boolean.")

        assert self._playwright_context is not None
        assert self._playwright_error_cls is not None
        assert self._playwright_timeout_cls is not None
        session = PlaywrightSession(
            playwright_context=self._playwright_context,
            playwright_error_cls=self._playwright_error_cls,
            playwright_timeout_cls=self._playwright_timeout_cls,
            headless=headless,
        )
        session_id = _new_session_id()
        with self._lock:
            self._sessions[session_id] = session
            self._active_session_id = session_id
        return session_id

    def close_session(self, session_id: str | None) -> str:
        resolved_session_id, session = self.resolve_session(session_id)
        with self._lock:
            self._sessions.pop(resolved_session_id, None)
            if self._active_session_id == resolved_session_id:
                self._active_session_id = next(reversed(self._sessions), None) if self._sessions else None
        session.close()
        return resolved_session_id

    def resolve_session(self, session_id: str | None) -> tuple[str, PlaywrightSession]:
        with self._lock:
            if session_id is None:
                resolved = self._active_session_id
            else:
                resolved = session_id

            if not isinstance(resolved, str) or not resolved:
                raise BrowserWorkerActionError(
                    "session_not_available",
                    "No browser session available. Provide session_id or open a session first.",
                )

            session = self._sessions.get(resolved)
            if session is None:
                raise BrowserWorkerActionError(
                    "session_not_available",
                    f"Session '{resolved}' is not available.",
                    {"session_id": resolved},
                )
            self._active_session_id = resolved
            return resolved, session

    def list_session_ids(self) -> list[str]:
        with self._lock:
            return list(self._sessions.keys())

    def shutdown(self) -> None:
        with self._lock:
            session_items = list(self._sessions.items())
            self._sessions = {}
            self._active_session_id = None

        for _, session in session_items:
            try:
                session.close()
            except Exception:
                pass

        if self._playwright_context is not None:
            try:
                self._playwright_context.stop()
            except Exception:
                pass

    def _initialize_playwright_runtime(self) -> None:
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            self._playwright_available = False
            self._playwright_error_message = str(exc)
            return

        try:
            playwright_driver = sync_playwright().start()
        except Exception as exc:
            self._playwright_available = False
            self._playwright_error_message = str(exc)
            return

        self._playwright_context = playwright_driver
        self._playwright_error_cls = PlaywrightError
        self._playwright_timeout_cls = PlaywrightTimeoutError
        self._playwright_available = True

    def _ensure_playwright_available(self) -> None:
        if self._playwright_available:
            return
        details = {}
        if self._playwright_error_message:
            details["reason"] = self._playwright_error_message
        raise BrowserWorkerActionError(
            "playwright_not_installed",
            "Playwright is not installed or could not be initialized in browser worker.",
            details,
        )


def _new_session_id() -> str:
    return f"session_{uuid.uuid4().hex[:12]}"


def _compute_in_viewport(bounding_box: dict[str, float], viewport: dict[str, Any]) -> bool:
    width = float(viewport.get("width", 0) or 0)
    height = float(viewport.get("height", 0) or 0)
    if width <= 0 or height <= 0:
        return False

    x = float(bounding_box.get("x", 0.0))
    y = float(bounding_box.get("y", 0.0))
    box_w = float(bounding_box.get("width", 0.0))
    box_h = float(bounding_box.get("height", 0.0))
    if box_w <= 0 or box_h <= 0:
        return False

    return (x + box_w) > 0 and (y + box_h) > 0 and x < width and y < height
