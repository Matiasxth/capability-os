from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .dom_introspection import DOMIntrospectionEngine
from .element_mapper import ElementMapper
from .element_registry import ElementRegistry
from .session_manager import BrowserWorkerActionError, BrowserWorkerSessionManager

ALIASES = {
    "browser_click": "browser_click_element",
    "browser_type": "browser_type_text",
    "browser_wait_for": "browser_wait_for_selector",
    "browser_screenshot": "browser_take_screenshot",
}


class BrowserActionExecutor:
    def __init__(
        self,
        session_manager: BrowserWorkerSessionManager,
        *,
        dom_introspection: DOMIntrospectionEngine | None = None,
        element_mapper: ElementMapper | None = None,
        element_registry: ElementRegistry | None = None,
    ):
        self.session_manager = session_manager
        self.dom_introspection = dom_introspection or DOMIntrospectionEngine()
        self.element_mapper = element_mapper or ElementMapper()
        self.element_registry = element_registry or ElementRegistry()

    def execute(
        self,
        *,
        action: str,
        session_id: str | None,
        payload: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise BrowserWorkerActionError("invalid_input", "Field 'payload' must be an object.")
        if not isinstance(metadata, dict):
            metadata = {}

        canonical_action = ALIASES.get(action, action)
        timeout_ms = _resolve_timeout_ms(payload, metadata)

        if canonical_action == "browser_open_session":
            return self._open_session(payload=payload, timeout_ms=timeout_ms)
        if canonical_action == "browser_close_session":
            return self._close_session(session_id=session_id)
        if canonical_action == "browser_navigate":
            return self._navigate(session_id=session_id, payload=payload, timeout_ms=timeout_ms)
        if canonical_action == "browser_click_element":
            return self._click_element(session_id=session_id, payload=payload, timeout_ms=timeout_ms)
        if canonical_action == "browser_type_text":
            return self._type_text(session_id=session_id, payload=payload, timeout_ms=timeout_ms)
        if canonical_action == "browser_read_text":
            return self._read_text(session_id=session_id, payload=payload, timeout_ms=timeout_ms)
        if canonical_action == "browser_wait_for_selector":
            return self._wait_for_selector(session_id=session_id, payload=payload, timeout_ms=timeout_ms)
        if canonical_action == "browser_take_screenshot":
            return self._take_screenshot(session_id=session_id, payload=payload, timeout_ms=timeout_ms)
        if canonical_action == "browser_list_tabs":
            return self._list_tabs(session_id=session_id)
        if canonical_action == "browser_switch_tab":
            return self._switch_tab(session_id=session_id, payload=payload)
        if canonical_action == "browser_list_interactive_elements":
            return self._list_interactive_elements(
                session_id=session_id,
                payload=payload,
                timeout_ms=timeout_ms,
            )
        if canonical_action == "browser_click_element_by_id":
            return self._click_element_by_id(
                session_id=session_id,
                payload=payload,
                timeout_ms=timeout_ms,
            )
        if canonical_action == "browser_type_into_element":
            return self._type_into_element(
                session_id=session_id,
                payload=payload,
                timeout_ms=timeout_ms,
            )
        if canonical_action == "browser_highlight_element":
            return self._highlight_element(
                session_id=session_id,
                payload=payload,
                timeout_ms=timeout_ms,
            )

        raise BrowserWorkerActionError(
            "browser_action_not_supported",
            f"Browser action '{action}' is not supported by worker.",
            {"action": action},
        )

    def _open_session(self, *, payload: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        headless = payload.get("headless", True)
        if not isinstance(headless, bool):
            raise BrowserWorkerActionError("invalid_input", "Field 'headless' must be a boolean.")

        cdp_endpoint = payload.get("cdp_endpoint")
        if cdp_endpoint is not None and not isinstance(cdp_endpoint, str):
            cdp_endpoint = None

        session_id, cdp_attached = self.session_manager.open_session(
            headless=headless, cdp_endpoint=cdp_endpoint,
        )
        result: dict[str, Any] = {
            "status": "success",
            "session_id": session_id,
            "cdp_attached": cdp_attached,
        }
        self.element_registry.invalidate(session_id=session_id)

        start_url = payload.get("start_url")
        if start_url not in (None, ""):
            url = _require_url(start_url)
            _, session = self.session_manager.resolve_session(session_id)
            navigation = session.navigate(url, timeout_ms)
            self.element_registry.invalidate(session_id=session_id)
            result["url"] = navigation.get("url", url)
            result["status_code"] = navigation.get("status_code", 0)

        return result

    def _close_session(self, *, session_id: str | None) -> dict[str, Any]:
        closed_session_id = self.session_manager.close_session(session_id)
        self.element_registry.invalidate(session_id=closed_session_id)
        return {"status": "success", "session_id": closed_session_id}

    def _navigate(self, *, session_id: str | None, payload: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        url = _require_url(payload.get("url"))
        resolved_session_id, session = self.session_manager.resolve_session(session_id)
        result = session.navigate(url, timeout_ms)
        self.element_registry.invalidate(session_id=resolved_session_id)
        result["session_id"] = resolved_session_id
        return result

    def _click_element(self, *, session_id: str | None, payload: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        selector = _require_selector(payload.get("selector"))
        resolved_session_id, session = self.session_manager.resolve_session(session_id)
        result = session.click(selector, timeout_ms)
        result["session_id"] = resolved_session_id
        return result

    def _type_text(self, *, session_id: str | None, payload: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        selector = _require_selector(payload.get("selector"))
        text = _require_string(payload.get("text"), "text")
        resolved_session_id, session = self.session_manager.resolve_session(session_id)
        result = session.type_text(selector, text, timeout_ms)
        result["session_id"] = resolved_session_id
        return result

    def _read_text(self, *, session_id: str | None, payload: dict[str, Any], timeout_ms: int) -> dict[str, Any]:
        selector_raw = payload.get("selector")
        selector = None if selector_raw in (None, "") else _require_selector(selector_raw)
        resolved_session_id, session = self.session_manager.resolve_session(session_id)
        result = session.read_text(selector, timeout_ms)
        result["session_id"] = resolved_session_id
        return result

    def _wait_for_selector(
        self,
        *,
        session_id: str | None,
        payload: dict[str, Any],
        timeout_ms: int,
    ) -> dict[str, Any]:
        selector = _require_selector(payload.get("selector"))
        resolved_session_id, session = self.session_manager.resolve_session(session_id)
        result = session.wait_for_selector(selector, timeout_ms)
        result["session_id"] = resolved_session_id
        return result

    def _take_screenshot(
        self,
        *,
        session_id: str | None,
        payload: dict[str, Any],
        timeout_ms: int,
    ) -> dict[str, Any]:
        raw_path = payload.get("path")
        if raw_path in (None, ""):
            raise BrowserWorkerActionError("invalid_input", "Field 'path' is required for screenshot action.")
        path = _resolve_workspace_path(self.session_manager.workspace_root, raw_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        full_page = payload.get("full_page", False)
        if not isinstance(full_page, bool):
            raise BrowserWorkerActionError("invalid_input", "Field 'full_page' must be a boolean.")

        resolved_session_id, session = self.session_manager.resolve_session(session_id)
        result = session.take_screenshot(path, full_page, timeout_ms)
        result["session_id"] = resolved_session_id
        result["path"] = str(path)
        return result

    def _list_tabs(self, *, session_id: str | None) -> dict[str, Any]:
        resolved_session_id, session = self.session_manager.resolve_session(session_id)
        result = session.list_tabs()
        result["session_id"] = resolved_session_id
        return result

    def _switch_tab(self, *, session_id: str | None, payload: dict[str, Any]) -> dict[str, Any]:
        tab_index = payload.get("tab_index")
        if not isinstance(tab_index, int):
            raise BrowserWorkerActionError("invalid_input", "Field 'tab_index' must be an integer.")
        resolved_session_id, session = self.session_manager.resolve_session(session_id)
        result = session.switch_tab(tab_index)
        self.element_registry.invalidate(session_id=resolved_session_id)
        result["session_id"] = resolved_session_id
        return result

    def _list_interactive_elements(
        self,
        *,
        session_id: str | None,
        payload: dict[str, Any],
        timeout_ms: int,
    ) -> dict[str, Any]:
        resolved_session_id, session = self.session_manager.resolve_session(session_id)
        filters = _parse_filters(payload)
        limit = _read_positive_int(payload.get("limit"), "limit", 300, max_value=1000)

        raw_elements = self.dom_introspection.extract_interactive_elements(
            session.active_page(),
            visible_only=filters["visible_only"],
            in_viewport_only=filters["in_viewport_only"],
            text_contains=filters["text_contains"],
            limit=limit,
        )
        mapped_elements = self.element_mapper.map_elements(raw_elements)
        registered_elements = self.element_registry.reconcile(
            session_id=resolved_session_id,
            page_url=session.current_url(),
            mapped_elements=mapped_elements,
        )
        return {
            "status": "success",
            "session_id": resolved_session_id,
            "elements": registered_elements,
            "count": len(registered_elements),
        }

    def _click_element_by_id(
        self,
        *,
        session_id: str | None,
        payload: dict[str, Any],
        timeout_ms: int,
    ) -> dict[str, Any]:
        element_id = _require_non_empty_string(payload.get("element_id"), "element_id")
        resolved_session_id, session = self.session_manager.resolve_session(session_id)
        record = self.element_registry.get(session_id=resolved_session_id, element_id=element_id)
        if record is None:
            raise BrowserWorkerActionError(
                "element_not_found",
                f"Element '{element_id}' was not found for session '{resolved_session_id}'.",
                {"element_id": element_id, "session_id": resolved_session_id},
            )

        selector = _require_non_empty_string(record.get("selector"), "selector")
        state = session.describe_element(selector, timeout_ms=min(timeout_ms, 1500))
        _ensure_element_interactable(
            state=state,
            record=record,
            element_id=element_id,
            session_id=resolved_session_id,
            selector=selector,
        )

        try:
            result = session.click(selector, timeout_ms)
        except BrowserWorkerActionError as exc:
            if exc.error_code == "selector_not_found":
                self.element_registry.remove(session_id=resolved_session_id, element_id=element_id)
                raise BrowserWorkerActionError(
                    "element_stale",
                    f"Element '{element_id}' is stale and can no longer be resolved.",
                    {"element_id": element_id, "session_id": resolved_session_id},
                ) from exc
            raise

        result["session_id"] = resolved_session_id
        result["element_id"] = element_id
        result["selector"] = selector
        return result

    def _type_into_element(
        self,
        *,
        session_id: str | None,
        payload: dict[str, Any],
        timeout_ms: int,
    ) -> dict[str, Any]:
        element_id = _require_non_empty_string(payload.get("element_id"), "element_id")
        text = _require_string(payload.get("text"), "text")
        resolved_session_id, session = self.session_manager.resolve_session(session_id)
        record = self.element_registry.get(session_id=resolved_session_id, element_id=element_id)
        if record is None:
            raise BrowserWorkerActionError(
                "element_not_found",
                f"Element '{element_id}' was not found for session '{resolved_session_id}'.",
                {"element_id": element_id, "session_id": resolved_session_id},
            )

        selector = _require_non_empty_string(record.get("selector"), "selector")
        state = session.describe_element(selector, timeout_ms=min(timeout_ms, 1500))
        _ensure_element_interactable(
            state=state,
            record=record,
            element_id=element_id,
            session_id=resolved_session_id,
            selector=selector,
        )

        try:
            result = session.type_text(selector, text, timeout_ms)
        except BrowserWorkerActionError as exc:
            if exc.error_code == "selector_not_found":
                self.element_registry.remove(session_id=resolved_session_id, element_id=element_id)
                raise BrowserWorkerActionError(
                    "element_stale",
                    f"Element '{element_id}' is stale and can no longer be resolved.",
                    {"element_id": element_id, "session_id": resolved_session_id},
                ) from exc
            if exc.error_code == "type_failed":
                raise BrowserWorkerActionError(
                    "element_not_interactable",
                    f"Element '{element_id}' is not interactable for typing.",
                    {"element_id": element_id, "session_id": resolved_session_id},
                ) from exc
            raise

        result["session_id"] = resolved_session_id
        result["element_id"] = element_id
        result["selector"] = selector
        return result

    def _highlight_element(
        self,
        *,
        session_id: str | None,
        payload: dict[str, Any],
        timeout_ms: int,
    ) -> dict[str, Any]:
        element_id = _require_non_empty_string(payload.get("element_id"), "element_id")
        duration_ms = _read_positive_int(payload.get("duration_ms"), "duration_ms", 1200, max_value=15000)
        resolved_session_id, session = self.session_manager.resolve_session(session_id)
        record = self.element_registry.get(session_id=resolved_session_id, element_id=element_id)
        if record is None:
            raise BrowserWorkerActionError(
                "element_not_found",
                f"Element '{element_id}' was not found for session '{resolved_session_id}'.",
                {"element_id": element_id, "session_id": resolved_session_id},
            )

        selector = _require_non_empty_string(record.get("selector"), "selector")
        state = session.describe_element(selector, timeout_ms=min(timeout_ms, 1500))
        if not state.get("exists", False):
            self.element_registry.remove(session_id=resolved_session_id, element_id=element_id)
            raise BrowserWorkerActionError(
                "element_stale",
                f"Element '{element_id}' is stale and can no longer be resolved.",
                {"element_id": element_id, "session_id": resolved_session_id},
            )
        result = session.highlight(selector, duration_ms, timeout_ms)
        result["session_id"] = resolved_session_id
        result["element_id"] = element_id
        return result


def _resolve_timeout_ms(payload: dict[str, Any], metadata: dict[str, Any]) -> int:
    timeout = metadata.get("timeout_ms", payload.get("timeout_ms", 15000))
    if not isinstance(timeout, int) or timeout <= 0:
        raise BrowserWorkerActionError("invalid_input", "Field 'timeout_ms' must be a positive integer.")
    return timeout


def _parse_filters(payload: dict[str, Any]) -> dict[str, Any]:
    filters = payload.get("filters", {})
    if filters is None:
        filters = {}
    if not isinstance(filters, dict):
        raise BrowserWorkerActionError("invalid_input", "Field 'filters' must be an object when provided.")

    visible_only = filters.get("visible_only", payload.get("visible_only", True))
    in_viewport_only = filters.get("in_viewport_only", payload.get("in_viewport_only", False))
    text_contains = filters.get("text_contains", payload.get("text_contains"))

    if not isinstance(visible_only, bool):
        raise BrowserWorkerActionError("invalid_input", "Filter 'visible_only' must be boolean.")
    if not isinstance(in_viewport_only, bool):
        raise BrowserWorkerActionError("invalid_input", "Filter 'in_viewport_only' must be boolean.")
    if text_contains not in (None, "") and not isinstance(text_contains, str):
        raise BrowserWorkerActionError("invalid_input", "Filter 'text_contains' must be string when provided.")

    return {
        "visible_only": visible_only,
        "in_viewport_only": in_viewport_only,
        "text_contains": None if text_contains in (None, "") else text_contains,
    }


def _read_positive_int(value: Any, field_name: str, default: int, *, max_value: int | None = None) -> int:
    if value is None:
        result = default
    else:
        if not isinstance(value, int) or value <= 0:
            raise BrowserWorkerActionError("invalid_input", f"Field '{field_name}' must be a positive integer.")
        result = value
    if max_value is not None and result > max_value:
        result = max_value
    return result


def _ensure_element_interactable(
    *,
    state: dict[str, Any],
    record: dict[str, Any],
    element_id: str,
    session_id: str,
    selector: str,
) -> None:
    if not state.get("exists", False):
        raise BrowserWorkerActionError(
            "element_stale",
            f"Element '{element_id}' is stale and can no longer be resolved.",
            {"element_id": element_id, "session_id": session_id},
        )
    if not state.get("visible", False):
        raise BrowserWorkerActionError(
            "element_not_visible",
            f"Element '{element_id}' is not visible.",
            {"element_id": element_id, "session_id": session_id, "selector": selector},
        )
    if not state.get("enabled", False):
        raise BrowserWorkerActionError(
            "element_not_interactable",
            f"Element '{element_id}' is disabled or not interactable.",
            {"element_id": element_id, "session_id": session_id, "selector": selector},
        )
    if not state.get("in_viewport", False):
        raise BrowserWorkerActionError(
            "element_out_of_view",
            f"Element '{element_id}' is outside viewport.",
            {
                "element_id": element_id,
                "session_id": session_id,
                "selector": selector,
                "bounding_box": state.get("bounding_box", {}),
            },
        )

    record_visible = bool(record.get("visible", True))
    if not record_visible:
        raise BrowserWorkerActionError(
            "element_not_visible",
            f"Element '{element_id}' is not visible according to registry snapshot.",
            {"element_id": element_id, "session_id": session_id},
        )


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BrowserWorkerActionError("invalid_input", f"Field '{field_name}' must be a non-empty string.")
    return value.strip()


def _require_selector(value: Any) -> str:
    selector = _require_non_empty_string(value, "selector")
    lowered = selector.lower()
    if lowered in {"click", "type", "wait", "wait_for_selector", "navigate", "open", "close"}:
        raise BrowserWorkerActionError(
            "invalid_input",
            (
                f"Field 'selector' has invalid value '{selector}'. "
                "Provide a real CSS selector like '#id', '.class', 'button', or '[aria-label=\"...\"]'."
            ),
        )
    return selector


def _require_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise BrowserWorkerActionError("invalid_input", f"Field '{field_name}' must be a string.")
    return value


def _require_url(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BrowserWorkerActionError("invalid_input", "Field 'url' must be a non-empty string.")
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise BrowserWorkerActionError("invalid_url", f"URL '{value}' must start with http:// or https://.")
    return value.strip()


def _resolve_workspace_path(workspace_root: Path, path_value: Any) -> Path:
    if not isinstance(path_value, str) or not path_value.strip():
        raise BrowserWorkerActionError("invalid_input", "Field 'path' must be a non-empty string.")

    root = workspace_root.resolve()
    raw_path = Path(path_value.strip())
    candidate = raw_path if raw_path.is_absolute() else (root / raw_path)
    resolved = candidate.resolve()

    try:
        common = os.path.commonpath([str(root), str(resolved)])
    except ValueError as exc:
        raise BrowserWorkerActionError(
            "workspace_violation",
            f"Path '{path_value}' is outside worker workspace.",
            {"path": path_value},
        ) from exc

    if Path(common) != root:
        raise BrowserWorkerActionError(
            "workspace_violation",
            f"Path '{path_value}' is outside worker workspace.",
            {"path": path_value},
        )

    return resolved
