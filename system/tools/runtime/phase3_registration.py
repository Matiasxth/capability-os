from __future__ import annotations

from pathlib import Path

from system.tools.implementations.phase3_tools import (
    execution_run_command,
    filesystem_list_directory,
    filesystem_read_file,
    filesystem_write_file,
    network_http_get,
)
from .tool_runtime import ToolRuntime


def register_phase3_real_tools(tool_runtime: ToolRuntime, workspace_root: str | Path) -> None:
    root = Path(workspace_root).resolve()

    tool_runtime.register_handler(
        "filesystem_read_file",
        lambda params, contract, ctx: filesystem_read_file(params, contract, root),
    )
    tool_runtime.register_handler(
        "filesystem_write_file",
        lambda params, contract, ctx: filesystem_write_file(params, contract, root),
    )
    tool_runtime.register_handler(
        "filesystem_list_directory",
        lambda params, contract, ctx: filesystem_list_directory(params, contract, root),
    )
    tool_runtime.register_handler(
        "execution_run_command",
        lambda params, contract, ctx: execution_run_command(params, contract, root),
    )
    tool_runtime.register_handler(
        "network_http_get",
        lambda params, contract, ctx: network_http_get(params, contract, root),
    )

