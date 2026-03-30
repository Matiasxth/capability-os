from __future__ import annotations

from pathlib import Path
from typing import Any

from system.tools.implementations.phase9_browser_tools import (
    BrowserSessionManager,
)
from system.tools.browser_ipc import BrowserIPCClient

from .tool_runtime import ToolRuntime


def register_phase9_browser_tools(
    tool_runtime: ToolRuntime,
    workspace_root: str | Path,
    ipc_client: BrowserIPCClient | None = None,
    **kwargs: Any,
) -> BrowserSessionManager:
    artifacts_root = kwargs.get("artifacts_root")
    auto_start = kwargs.get("auto_start", True)
    cdp_port = kwargs.get("cdp_port", 0)
    auto_restart_max_retries = kwargs.get("auto_restart_max_retries", 2)
    backend = kwargs.get("backend", "playwright")
    manager = BrowserSessionManager(
        workspace_root=workspace_root,
        ipc_client=ipc_client,
        artifacts_root=artifacts_root,
        auto_start=auto_start,
        cdp_port=cdp_port,
        auto_restart_max_retries=auto_restart_max_retries,
        backend=backend,
    )

    tool_runtime.register_handler(
        "browser_open_session",
        lambda params, contract, ctx: manager.open_session(params, contract),
    )
    tool_runtime.register_handler(
        "browser_close_session",
        lambda params, contract, ctx: manager.close_session(params, contract),
    )
    tool_runtime.register_handler(
        "browser_navigate",
        lambda params, contract, ctx: manager.navigate(params, contract),
    )
    tool_runtime.register_handler(
        "browser_click_element",
        lambda params, contract, ctx: manager.click(params, contract),
    )
    tool_runtime.register_handler(
        "browser_type_text",
        lambda params, contract, ctx: manager.type_text(params, contract),
    )
    tool_runtime.register_handler(
        "browser_read_text",
        lambda params, contract, ctx: manager.read_text(params, contract),
    )
    tool_runtime.register_handler(
        "browser_wait_for_selector",
        lambda params, contract, ctx: manager.wait_for(params, contract),
    )
    tool_runtime.register_handler(
        "browser_take_screenshot",
        lambda params, contract, ctx: manager.screenshot(params, contract),
    )
    tool_runtime.register_handler(
        "browser_list_tabs",
        lambda params, contract, ctx: manager.list_tabs(params, contract),
    )
    tool_runtime.register_handler(
        "browser_switch_tab",
        lambda params, contract, ctx: manager.switch_tab(params, contract),
    )
    tool_runtime.register_handler(
        "browser_list_interactive_elements",
        lambda params, contract, ctx: manager.list_interactive_elements(params, contract),
    )
    tool_runtime.register_handler(
        "browser_click_element_by_id",
        lambda params, contract, ctx: manager.click_element_by_id(params, contract),
    )
    tool_runtime.register_handler(
        "browser_type_into_element",
        lambda params, contract, ctx: manager.type_into_element(params, contract),
    )
    tool_runtime.register_handler(
        "browser_highlight_element",
        lambda params, contract, ctx: manager.highlight_element(params, contract),
    )
    tool_runtime.register_alias("browser_click", "browser_click_element")
    tool_runtime.register_alias("browser_type", "browser_type_text")
    tool_runtime.register_alias("browser_wait_for", "browser_wait_for_selector")
    tool_runtime.register_alias("browser_screenshot", "browser_take_screenshot")

    return manager
