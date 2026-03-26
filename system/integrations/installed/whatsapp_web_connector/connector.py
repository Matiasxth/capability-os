from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from system.tools.runtime import ToolExecutionError, ToolRuntime


class WhatsAppConnectorError(RuntimeError):
    """Structured connector error for WhatsApp Web v1."""

    def __init__(self, error_code: str, error_message: str, details: dict[str, Any] | None = None):
        super().__init__(error_message)
        self.error_code = error_code
        self.error_message = error_message
        self.details = details or {}


class WhatsAppWebConnector:
    """Assisted WhatsApp Web connector over the Browser Control Layer."""

    _SESSION_ERROR_CODES = {"session_not_available", "session_not_found"}
    _TRANSIENT_SELECTOR_ERROR_CODES = {"selector_not_found", "wait_failed"}
    _TRANSIENT_ELEMENT_ERROR_CODES = {
        "element_not_found",
        "element_not_visible",
        "element_not_interactable",
        "element_stale",
        "element_out_of_view",
    }
    _SELECTOR_PROBE_TIMEOUT_MS = 1200
    _SEARCH_INTERACTION_TIMEOUT_CAP_MS = 3000
    _SEARCH_DOM_LIST_TIMEOUT_CAP_MS = 2500
    _SEARCH_DOM_LIST_LIMIT = 300
    _SEND_CLICK_TIMEOUT_CAP_MS = 4000
    _SEND_FALLBACK_CLICK_TIMEOUT_MS = 1200

    def __init__(self, tool_runtime: ToolRuntime, selectors_config_path: str | Path):
        self.tool_runtime = tool_runtime
        self.selectors_config_path = Path(selectors_config_path).resolve()
        self.config = self._load_selectors_config(self.selectors_config_path)

        self.base_url = self._read_url(self.config.get("base_url"))
        self.default_timeout_ms = _read_positive_int(self.config.get("default_timeout_ms"), "default_timeout_ms", 15000)
        self.default_poll_interval_ms = _read_positive_int(
            self.config.get("default_poll_interval_ms"),
            "default_poll_interval_ms",
            2000,
        )

        self.login_authenticated_selectors = _read_selector_list(
            self.config,
            ("login", "authenticated_selectors"),
            required=True,
        )
        self.login_qr_visible_selectors = _read_selector_list(
            self.config,
            ("login", "qr_visible_selectors"),
            required=True,
        )
        self.chat_search_selectors = _read_selector_list(
            self.config,
            ("chat", "search_input_selectors"),
            required=True,
        )
        self.chat_results_selectors = _read_selector_list(
            self.config,
            ("chat", "results_list_selectors"),
            required=True,
        )
        self.chat_visible_list_selectors = _read_selector_list(
            self.config,
            ("chat", "visible_list_selectors"),
            required=True,
        )
        self.chat_row_selector_template = _read_nested_string(
            self.config,
            ("chat", "chat_row_selector_template"),
            required=True,
        )
        self.message_list_selectors = _read_selector_list(
            self.config,
            ("message", "message_list_selectors"),
            required=True,
        )
        self.composer_input_selectors = _read_selector_list(
            self.config,
            ("message", "composer_input_selectors"),
            required=True,
        )
        self.send_button_selectors = _read_selector_list(
            self.config,
            ("message", "send_button_selectors"),
            required=True,
        )

    def open_whatsapp_web(self, inputs: dict[str, Any]) -> dict[str, Any]:
        session_id = _read_optional_string(inputs.get("session_id"), "session_id")
        headless = inputs.get("headless", False)
        if not isinstance(headless, bool):
            raise WhatsAppConnectorError("invalid_input", "Field 'headless' must be boolean when provided.")

        timeout_ms = _read_positive_int(inputs.get("timeout_ms"), "timeout_ms", self.default_timeout_ms)
        url = self._read_url(inputs.get("url", self.base_url))

        if session_id is None:
            try:
                navigate_output = self._execute_tool("browser_navigate", {"url": url, "timeout_ms": timeout_ms})
            except WhatsAppConnectorError as exc:
                if exc.error_code not in self._SESSION_ERROR_CODES:
                    raise
                opened = self._execute_tool(
                    "browser_open_session",
                    {"headless": headless, "start_url": url, "timeout_ms": timeout_ms},
                )
                session_id = _require_result_string(opened, "session_id", "browser_open_session")
                final_url = _read_optional_string(opened.get("url"), "url") or url
                login_snapshot = self._detect_login_state(session_id, timeout_ms=min(timeout_ms, 1200))
                return {
                    "status": "success",
                    "session_id": session_id,
                    "url": final_url,
                    "login_state": login_snapshot["login_state"],
                }
            else:
                session_id = _require_result_string(navigate_output, "session_id", "browser_navigate")
                final_url = _read_optional_string(navigate_output.get("url"), "url") or url
                login_snapshot = self._detect_login_state(session_id, timeout_ms=min(timeout_ms, 1200))
                return {
                    "status": "success",
                    "session_id": session_id,
                    "url": final_url,
                    "login_state": login_snapshot["login_state"],
                }

        navigate_output = self._execute_tool(
            "browser_navigate",
            {"session_id": session_id, "url": url, "timeout_ms": timeout_ms},
        )
        resolved_session_id = _require_result_string(navigate_output, "session_id", "browser_navigate")
        final_url = _read_optional_string(navigate_output.get("url"), "url") or url
        login_snapshot = self._detect_login_state(resolved_session_id, timeout_ms=min(timeout_ms, 1200))
        return {
            "status": "success",
            "session_id": resolved_session_id,
            "url": final_url,
            "login_state": login_snapshot["login_state"],
        }

    def wait_for_whatsapp_login(self, inputs: dict[str, Any]) -> dict[str, Any]:
        session_id = _read_optional_string(inputs.get("session_id"), "session_id")
        timeout_ms = _read_positive_int(inputs.get("timeout_ms"), "timeout_ms", 60000)
        poll_interval_ms = _read_positive_int(
            inputs.get("poll_interval_ms"),
            "poll_interval_ms",
            self.default_poll_interval_ms,
        )
        if poll_interval_ms > timeout_ms:
            poll_interval_ms = timeout_ms

        started = time.monotonic()
        attempts = 0
        last_snapshot: dict[str, Any] = {"session_id": session_id, "login_state": "unknown", "url": None}

        while (time.monotonic() - started) * 1000 < timeout_ms:
            attempts += 1
            snapshot = self._detect_login_state(session_id, timeout_ms=min(2000, poll_interval_ms))
            last_snapshot = snapshot
            session_id = snapshot.get("session_id")
            login_state = snapshot.get("login_state")
            if login_state in {"qr_visible", "authenticated"}:
                return {
                    "status": "success",
                    "session_id": session_id,
                    "login_state": login_state,
                    "url": snapshot.get("url"),
                    "attempts": attempts,
                    "timeout_ms": timeout_ms,
                }
            if poll_interval_ms > 0:
                time.sleep(poll_interval_ms / 1000.0)

        return {
            "status": "success",
            "session_id": last_snapshot.get("session_id"),
            "login_state": "timeout",
            "url": last_snapshot.get("url"),
            "attempts": attempts,
            "timeout_ms": timeout_ms,
        }

    def search_whatsapp_chat(self, inputs: dict[str, Any]) -> dict[str, Any]:
        session_id = _read_optional_string(inputs.get("session_id"), "session_id")
        chat_name = _require_non_empty_string(inputs.get("chat_name"), "chat_name")
        timeout_ms = _read_positive_int(inputs.get("timeout_ms"), "timeout_ms", self.default_timeout_ms)

        search_resolution = self._focus_and_type_chat_search(
            session_id=session_id,
            chat_name=chat_name,
            timeout_ms=timeout_ms,
        )
        resolved_session_id = search_resolution["session_id"]

        results_selector = self._pick_selector(resolved_session_id, self.chat_results_selectors, timeout_ms)
        results_text = self._execute_tool(
            "browser_read_text",
            _with_session({"selector": results_selector, "timeout_ms": timeout_ms}, resolved_session_id),
        )
        lines = _normalize_lines(str(results_text.get("text", "")))
        lowered_query = chat_name.lower()
        matches = [line for line in lines if lowered_query in line.lower()]

        selected = False
        row_selector = self.chat_row_selector_template.format(chat_name=_escape_selector_value(chat_name))
        try:
            self._execute_tool(
                "browser_click_element",
                _with_session({"selector": row_selector, "timeout_ms": timeout_ms}, resolved_session_id),
            )
            selected = True
        except WhatsAppConnectorError as exc:
            if exc.error_code not in self._TRANSIENT_SELECTOR_ERROR_CODES:
                raise

        return {
            "status": "success" if (selected or matches) else "not_found",
            "session_id": resolved_session_id,
            "chat_name": chat_name,
            "selected": selected,
            "matches": matches[:20],
            "search_resolution": search_resolution,
        }

    def read_whatsapp_messages(self, inputs: dict[str, Any]) -> dict[str, Any]:
        session_id = _read_optional_string(inputs.get("session_id"), "session_id")
        max_messages = _read_positive_int(inputs.get("max_messages"), "max_messages", 20)
        timeout_ms = _read_positive_int(inputs.get("timeout_ms"), "timeout_ms", self.default_timeout_ms)

        messages_selector = self._pick_selector(session_id, self.message_list_selectors, timeout_ms)
        raw = self._execute_tool(
            "browser_read_text",
            _with_session({"selector": messages_selector, "timeout_ms": timeout_ms}, session_id),
        )
        resolved_session_id = _require_result_string(raw, "session_id", "browser_read_text")
        lines = _normalize_lines(str(raw.get("text", "")))
        visible = lines[-max_messages:]

        messages: list[dict[str, Any]] = []
        for index, text in enumerate(visible):
            messages.append({"index": index, "text": text})

        return {
            "status": "success",
            "session_id": resolved_session_id,
            "messages": messages,
            "message_count": len(messages),
            "scope": "visible_only",
        }

    def send_whatsapp_message(self, inputs: dict[str, Any]) -> dict[str, Any]:
        session_id = _read_optional_string(inputs.get("session_id"), "session_id")
        message = _require_non_empty_string(inputs.get("message"), "message")
        timeout_ms = _read_positive_int(inputs.get("timeout_ms"), "timeout_ms", self.default_timeout_ms)

        composer_selector = self._pick_selector(session_id, self.composer_input_selectors, timeout_ms)
        clicked = self._execute_tool(
            "browser_click_element",
            _with_session({"selector": composer_selector, "timeout_ms": timeout_ms}, session_id),
        )
        typed = self._execute_tool(
            "browser_type_text",
            _with_session(
                {"selector": composer_selector, "text": message, "timeout_ms": timeout_ms},
                clicked.get("session_id"),
            ),
        )
        resolved_session_id = _require_result_string(typed, "session_id", "browser_type_text")

        send_click_timeout_ms = min(timeout_ms, self._SEND_CLICK_TIMEOUT_CAP_MS)
        visible_send_selectors: list[str] = []
        for selector in self.send_button_selectors:
            probe = self._probe_selector(
                resolved_session_id,
                selector,
                timeout_ms=min(send_click_timeout_ms, self._SELECTOR_PROBE_TIMEOUT_MS),
            )
            if probe["visible"]:
                visible_send_selectors.append(selector)

        candidate_selectors = visible_send_selectors or list(self.send_button_selectors)
        click_timeout_ms = (
            send_click_timeout_ms
            if visible_send_selectors
            else min(send_click_timeout_ms, self._SEND_FALLBACK_CLICK_TIMEOUT_MS)
        )
        sent = False
        transient_failures: list[dict[str, str]] = []
        for selector in candidate_selectors:
            try:
                self._execute_tool(
                    "browser_click_element",
                    _with_session({"selector": selector, "timeout_ms": click_timeout_ms}, resolved_session_id),
                )
                sent = True
                break
            except WhatsAppConnectorError as exc:
                if exc.error_code not in self._TRANSIENT_SELECTOR_ERROR_CODES:
                    raise
                transient_failures.append({"selector": selector, "error_code": exc.error_code})

        if not sent:
            raise WhatsAppConnectorError(
                "send_button_not_found",
                "Could not find a WhatsApp send button for the active chat. Verify selector config for your WhatsApp Web variant.",
                {
                    "session_id": resolved_session_id,
                    "visible_send_selectors": visible_send_selectors,
                    "candidate_selectors": candidate_selectors,
                    "transient_failures": transient_failures[:10],
                },
            )

        return {
            "status": "success",
            "session_id": resolved_session_id,
            "message": message,
            "confirmation": "sent",
        }

    def list_whatsapp_visible_chats(self, inputs: dict[str, Any]) -> dict[str, Any]:
        session_id = _read_optional_string(inputs.get("session_id"), "session_id")
        max_chats = _read_positive_int(inputs.get("max_chats"), "max_chats", 30)
        timeout_ms = _read_positive_int(inputs.get("timeout_ms"), "timeout_ms", self.default_timeout_ms)

        list_selector = self._pick_selector(session_id, self.chat_visible_list_selectors, timeout_ms)
        raw = self._execute_tool(
            "browser_read_text",
            _with_session({"selector": list_selector, "timeout_ms": timeout_ms}, session_id),
        )
        resolved_session_id = _require_result_string(raw, "session_id", "browser_read_text")
        lines = _normalize_lines(str(raw.get("text", "")))

        seen: set[str] = set()
        chats: list[dict[str, Any]] = []
        for line in lines:
            if line in seen:
                continue
            seen.add(line)
            chats.append({"name": line})
            if len(chats) >= max_chats:
                break

        return {
            "status": "success",
            "session_id": resolved_session_id,
            "chats": chats,
            "chat_count": len(chats),
        }

    def _focus_and_type_chat_search(
        self,
        *,
        session_id: str | None,
        chat_name: str,
        timeout_ms: int,
    ) -> dict[str, Any]:
        interaction_timeout_ms = min(timeout_ms, self._SEARCH_INTERACTION_TIMEOUT_CAP_MS)
        selector_attempts: list[dict[str, str]] = []

        ordered_search_selectors = self._order_selectors_by_visibility(
            session_id=session_id,
            selectors=self.chat_search_selectors,
            timeout_ms=timeout_ms,
        )
        for selector in ordered_search_selectors:
            try:
                clicked = self._execute_tool(
                    "browser_click_element",
                    _with_session({"selector": selector, "timeout_ms": interaction_timeout_ms}, session_id),
                )
                resolved_session_id = _require_result_string(clicked, "session_id", "browser_click_element")
                typed = self._execute_tool(
                    "browser_type_text",
                    _with_session(
                        {"selector": selector, "text": chat_name, "timeout_ms": interaction_timeout_ms},
                        resolved_session_id,
                    ),
                )
                resolved_session_id = _require_result_string(typed, "session_id", "browser_type_text")
                return {
                    "mode": "selector",
                    "selector": selector,
                    "session_id": resolved_session_id,
                }
            except WhatsAppConnectorError as exc:
                if exc.error_code in self._search_transient_error_codes():
                    selector_attempts.append({"selector": selector, "error_code": exc.error_code})
                    continue
                raise

        dom_fallback = self._focus_and_type_chat_search_by_element_id(
            session_id=session_id,
            chat_name=chat_name,
            timeout_ms=timeout_ms,
        )
        if dom_fallback is not None:
            dom_fallback["selector_attempts"] = selector_attempts[:10]
            return dom_fallback

        raise WhatsAppConnectorError(
            "search_input_not_found",
            "Could not locate a WhatsApp search input for chat lookup.",
            {
                "session_id": session_id,
                "attempted_selectors": ordered_search_selectors,
                "selector_attempts": selector_attempts[:10],
            },
        )

    def _focus_and_type_chat_search_by_element_id(
        self,
        *,
        session_id: str | None,
        chat_name: str,
        timeout_ms: int,
    ) -> dict[str, Any] | None:
        list_timeout_ms = min(timeout_ms, self._SEARCH_DOM_LIST_TIMEOUT_CAP_MS)
        try:
            listed = self._execute_tool(
                "browser_list_interactive_elements",
                _with_session(
                    {
                        "filters": {"visible_only": True, "in_viewport_only": True},
                        "limit": self._SEARCH_DOM_LIST_LIMIT,
                        "timeout_ms": list_timeout_ms,
                    },
                    session_id,
                ),
            )
        except WhatsAppConnectorError as exc:
            # Backward compatible: if DOM tools are unavailable, keep selector-only behavior.
            if exc.error_code in {"browser_action_not_supported", "browser_tool_error"}:
                return None
            raise

        resolved_session_id = _require_result_string(
            listed,
            "session_id",
            "browser_list_interactive_elements",
        )
        elements = listed.get("elements")
        if not isinstance(elements, list) or not elements:
            return None

        ranked = self._rank_search_elements(elements)
        if not ranked:
            return None

        interaction_timeout_ms = min(timeout_ms, self._SEARCH_INTERACTION_TIMEOUT_CAP_MS)
        for candidate in ranked:
            element_id = candidate.get("element_id")
            if not isinstance(element_id, str) or not element_id:
                continue
            try:
                clicked = self._execute_tool(
                    "browser_click_element_by_id",
                    _with_session(
                        {"element_id": element_id, "timeout_ms": interaction_timeout_ms},
                        resolved_session_id,
                    ),
                )
                resolved_session_id = _require_result_string(clicked, "session_id", "browser_click_element_by_id")
                typed = self._execute_tool(
                    "browser_type_into_element",
                    _with_session(
                        {"element_id": element_id, "text": chat_name, "timeout_ms": interaction_timeout_ms},
                        resolved_session_id,
                    ),
                )
                resolved_session_id = _require_result_string(typed, "session_id", "browser_type_into_element")
                return {
                    "mode": "element_id",
                    "element_id": element_id,
                    "session_id": resolved_session_id,
                }
            except WhatsAppConnectorError as exc:
                if exc.error_code in self._search_transient_error_codes():
                    continue
                raise

        return None

    def _order_selectors_by_visibility(
        self,
        *,
        session_id: str | None,
        selectors: list[str],
        timeout_ms: int,
    ) -> list[str]:
        visible: list[str] = []
        non_visible: list[str] = []
        for selector in selectors:
            probe = self._probe_selector(
                session_id,
                selector,
                timeout_ms=min(timeout_ms, self._SELECTOR_PROBE_TIMEOUT_MS),
            )
            if probe["visible"]:
                visible.append(selector)
            else:
                non_visible.append(selector)
        ordered = visible + non_visible
        deduped: list[str] = []
        seen: set[str] = set()
        for selector in ordered:
            if selector in seen:
                continue
            seen.add(selector)
            deduped.append(selector)
        return deduped

    def _rank_search_elements(self, elements: list[Any]) -> list[dict[str, Any]]:
        ranked: list[tuple[int, dict[str, Any]]] = []
        for element in elements:
            if not isinstance(element, dict):
                continue
            if not bool(element.get("visible", False)):
                continue
            if not bool(element.get("enabled", False)):
                continue
            element_id = element.get("element_id")
            if not isinstance(element_id, str) or not element_id:
                continue

            element_type = str(element.get("type", "")).lower()
            text_blob = " ".join(
                [
                    str(element.get("text", "")),
                    str(element.get("aria_label", "")),
                    str(element.get("placeholder", "")),
                    str(element.get("selector", "")),
                    str((element.get("attributes") or {}).get("role", "")),
                ]
            ).lower()

            score = 0
            if "search" in text_blob or "buscar" in text_blob:
                score += 6
            if "chat" in text_blob or "chats" in text_blob:
                score += 4
            if "textbox" in text_blob:
                score += 2
            if element_type == "input":
                score += 2
            if element_type == "custom":
                score += 1

            if score <= 0:
                continue
            ranked.append((score, element))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in ranked]

    def _search_transient_error_codes(self) -> set[str]:
        return (
            set(self._TRANSIENT_SELECTOR_ERROR_CODES)
            | set(self._TRANSIENT_ELEMENT_ERROR_CODES)
            | {"click_failed", "type_failed"}
        )

    def _detect_login_state(self, session_id: str | None, timeout_ms: int) -> dict[str, Any]:
        for selector in self.login_authenticated_selectors:
            probe = self._probe_selector(
                session_id,
                selector,
                timeout_ms=min(timeout_ms, self._SELECTOR_PROBE_TIMEOUT_MS),
            )
            if probe["visible"]:
                return {
                    "session_id": probe.get("session_id"),
                    "login_state": "authenticated",
                    "url": probe.get("url"),
                }

        for selector in self.login_qr_visible_selectors:
            probe = self._probe_selector(
                session_id,
                selector,
                timeout_ms=min(timeout_ms, self._SELECTOR_PROBE_TIMEOUT_MS),
            )
            if probe["visible"]:
                return {
                    "session_id": probe.get("session_id"),
                    "login_state": "qr_visible",
                    "url": probe.get("url"),
                }

        body = self._execute_tool(
            "browser_read_text",
            _with_session({"selector": "body", "timeout_ms": min(timeout_ms, 1500)}, session_id),
        )
        resolved_session_id = _require_result_string(body, "session_id", "browser_read_text")
        lower_body = str(body.get("text", "")).lower()
        if ("qr" in lower_body and ("scan" in lower_body or "code" in lower_body)) or "codigo qr" in lower_body:
            login_state = "qr_visible"
        elif (
            ("chat" in lower_body and "search" in lower_body)
            or "new chat" in lower_body
            or "nuevo chat" in lower_body
        ):
            login_state = "authenticated"
        else:
            login_state = "unknown"
        return {
            "session_id": resolved_session_id,
            "login_state": login_state,
            "url": body.get("url"),
        }

    def _probe_selector(self, session_id: str | None, selector: str, timeout_ms: int) -> dict[str, Any]:
        try:
            result = self._execute_tool(
                "browser_wait_for_selector",
                _with_session({"selector": selector, "timeout_ms": timeout_ms}, session_id),
            )
            return {
                "visible": True,
                "session_id": result.get("session_id"),
                "url": result.get("url"),
            }
        except WhatsAppConnectorError as exc:
            if exc.error_code in self._TRANSIENT_SELECTOR_ERROR_CODES:
                return {
                    "visible": False,
                    "session_id": None,
                    "url": None,
                }
            raise

    def _pick_selector(self, session_id: str | None, selectors: list[str], timeout_ms: int) -> str:
        fallback = selectors[0]
        for selector in selectors:
            probe = self._probe_selector(
                session_id,
                selector,
                timeout_ms=min(timeout_ms, self._SELECTOR_PROBE_TIMEOUT_MS),
            )
            if probe["visible"]:
                return selector
        return fallback

    def _execute_tool(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self.tool_runtime.execute(action, params)
        except ToolExecutionError as exc:
            message = str(exc)
            error_code = _extract_error_code(message)
            raise WhatsAppConnectorError(
                error_code,
                f"Browser tool '{action}' failed ({error_code}).",
                {"action": action, "cause": message},
            ) from exc

        if not isinstance(result, dict):
            raise WhatsAppConnectorError(
                "invalid_tool_output",
                f"Browser tool '{action}' returned a non-object result.",
                {"action": action},
            )
        return result

    @staticmethod
    def _load_selectors_config(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise WhatsAppConnectorError(
                "config_not_found",
                f"WhatsApp selectors config was not found at '{path}'.",
            )
        with path.open("r", encoding="utf-8-sig") as handle:
            try:
                data = json.load(handle)
            except json.JSONDecodeError as exc:
                raise WhatsAppConnectorError(
                    "invalid_config",
                    f"Invalid JSON in selectors config '{path}': {exc}",
                ) from exc
        if not isinstance(data, dict):
            raise WhatsAppConnectorError("invalid_config", "Selectors config root must be an object.")
        return data

    @staticmethod
    def _read_url(raw_url: Any) -> str:
        if not isinstance(raw_url, str) or not raw_url.strip():
            raise WhatsAppConnectorError("invalid_config", "Configured WhatsApp URL must be a non-empty string.")
        url = raw_url.strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise WhatsAppConnectorError("invalid_config", f"Configured URL '{url}' is invalid.")
        return url


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WhatsAppConnectorError("invalid_input", f"Field '{field_name}' must be a non-empty string.")
    return value.strip()


def _read_optional_string(value: Any, field_name: str) -> str | None:
    if value in (None, ""):
        return None
    return _require_non_empty_string(value, field_name)


def _read_positive_int(value: Any, field_name: str, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or value <= 0:
        raise WhatsAppConnectorError("invalid_input", f"Field '{field_name}' must be a positive integer.")
    return value


def _with_session(payload: dict[str, Any], session_id: Any) -> dict[str, Any]:
    data = dict(payload)
    if isinstance(session_id, str) and session_id:
        data["session_id"] = session_id
    return data


def _extract_error_code(message: str) -> str:
    match = re.search(r'"error_code"\s*:\s*"([a-z0-9_]+)"', message)
    if match is not None:
        return match.group(1)

    known_codes = (
        "session_not_available",
        "session_not_found",
        "selector_not_found",
        "search_input_not_found",
        "navigation_timeout",
        "navigation_failed",
        "click_failed",
        "type_failed",
        "wait_failed",
        "read_text_failed",
        "element_not_found",
        "element_not_visible",
        "element_not_interactable",
        "element_stale",
        "element_out_of_view",
        "invalid_input",
    )
    lower = message.lower()
    for code in known_codes:
        if code in lower:
            return code
    return "browser_tool_error"


def _read_selector_list(config: dict[str, Any], path: tuple[str, ...], *, required: bool) -> list[str]:
    node: Any = config
    for token in path:
        if isinstance(node, dict) and token in node:
            node = node[token]
        else:
            if required:
                joined = ".".join(path)
                raise WhatsAppConnectorError("invalid_config", f"Missing selectors config key '{joined}'.")
            return []

    if isinstance(node, str):
        values = [node]
    elif isinstance(node, list):
        values = node
    else:
        joined = ".".join(path)
        raise WhatsAppConnectorError("invalid_config", f"Key '{joined}' must be a string or array.")

    selectors: list[str] = []
    for item in values:
        if not isinstance(item, str) or not item.strip():
            joined = ".".join(path)
            raise WhatsAppConnectorError(
                "invalid_config",
                f"Key '{joined}' contains an invalid selector entry.",
            )
        selectors.append(item.strip())
    if required and not selectors:
        joined = ".".join(path)
        raise WhatsAppConnectorError("invalid_config", f"Key '{joined}' must include at least one selector.")
    return selectors


def _read_nested_string(config: dict[str, Any], path: tuple[str, ...], *, required: bool) -> str:
    node: Any = config
    for token in path:
        if isinstance(node, dict) and token in node:
            node = node[token]
        else:
            if required:
                joined = ".".join(path)
                raise WhatsAppConnectorError("invalid_config", f"Missing config key '{joined}'.")
            return ""
    if not isinstance(node, str) or not node.strip():
        joined = ".".join(path)
        raise WhatsAppConnectorError("invalid_config", f"Key '{joined}' must be a non-empty string.")
    return node.strip()


def _normalize_lines(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        lines.append(cleaned)
    return lines


def _escape_selector_value(raw: str) -> str:
    return raw.replace("\\", "\\\\").replace('"', '\\"')


def _require_result_string(result: dict[str, Any], field: str, action: str) -> str:
    value = result.get(field)
    if not isinstance(value, str) or not value.strip():
        raise WhatsAppConnectorError(
            "invalid_tool_output",
            f"Browser tool '{action}' did not return a valid '{field}'.",
            {"action": action},
        )
    return value.strip()
