from __future__ import annotations

from pathlib import Path

from system.tools.implementations.phase3_tools import (
    execution_list_processes,
    execution_read_process_output,
    execution_run_command,
    execution_run_script,
    execution_terminate_process,
    filesystem_copy_file,
    filesystem_delete_file,
    filesystem_edit_file,
    filesystem_list_directory,
    filesystem_move_file,
    filesystem_read_file,
    filesystem_write_file,
    network_extract_links,
    network_extract_text,
    network_http_get,
    network_http_post,
    network_parse_html,
    system_get_env_var,
    system_get_os_info,
    system_get_workspace_info,
)
from .tool_runtime import ToolRuntime


def register_phase3_real_tools(tool_runtime: ToolRuntime, workspace_root: str | Path, path_validator=None) -> None:
    root = Path(workspace_root).resolve()
    if path_validator is not None:
        from system.tools.implementations.phase3_tools import set_path_validator
        set_path_validator(path_validator)

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
    # --- Filesystem (Bloque 1) ---
    tool_runtime.register_handler(
        "filesystem_edit_file",
        lambda params, contract, ctx: filesystem_edit_file(params, contract, root),
    )
    tool_runtime.register_handler(
        "filesystem_copy_file",
        lambda params, contract, ctx: filesystem_copy_file(params, contract, root),
    )
    tool_runtime.register_handler(
        "filesystem_move_file",
        lambda params, contract, ctx: filesystem_move_file(params, contract, root),
    )
    tool_runtime.register_handler(
        "filesystem_delete_file",
        lambda params, contract, ctx: filesystem_delete_file(params, contract, root),
    )
    # --- Execution (Bloque 1) ---
    tool_runtime.register_handler(
        "execution_run_script",
        lambda params, contract, ctx: execution_run_script(params, contract, root),
    )
    tool_runtime.register_handler(
        "execution_list_processes",
        lambda params, contract, ctx: execution_list_processes(params, contract, root),
    )
    tool_runtime.register_handler(
        "execution_terminate_process",
        lambda params, contract, ctx: execution_terminate_process(params, contract, root),
    )
    tool_runtime.register_handler(
        "execution_read_process_output",
        lambda params, contract, ctx: execution_read_process_output(params, contract, root),
    )
    # --- Network (Bloque 1) ---
    tool_runtime.register_handler(
        "network_http_post",
        lambda params, contract, ctx: network_http_post(params, contract, root),
    )
    # --- Network HTML parsing (Bloque 2) ---
    tool_runtime.register_handler(
        "network_parse_html",
        lambda params, contract, ctx: network_parse_html(params, contract, root),
    )
    tool_runtime.register_handler(
        "network_extract_links",
        lambda params, contract, ctx: network_extract_links(params, contract, root),
    )
    tool_runtime.register_handler(
        "network_extract_text",
        lambda params, contract, ctx: network_extract_text(params, contract, root),
    )
    # --- System (Bloque 1) ---
    tool_runtime.register_handler(
        "system_get_os_info",
        lambda params, contract, ctx: system_get_os_info(params, contract, root),
    )
    tool_runtime.register_handler(
        "system_get_env_var",
        lambda params, contract, ctx: system_get_env_var(params, contract, root),
    )
    tool_runtime.register_handler(
        "system_get_workspace_info",
        lambda params, contract, ctx: system_get_workspace_info(params, contract, root),
    )

