from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class ToolSecurityError(PermissionError):
    """Raised when a tool violates workspace or command security constraints."""


def filesystem_read_file(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    target = _resolve_workspace_path(workspace_root, params.get("path"))
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"File '{target}' does not exist.")

    content = target.read_text(encoding="utf-8-sig")
    result = {
        "content": content,
        "path": str(target),
        "size_bytes": target.stat().st_size,
        "encoding": "utf-8-sig",
    }
    project_items = params.get("project_items")
    project_path = params.get("project_path")
    if isinstance(project_items, list) and isinstance(project_path, str):
        file_count = sum(1 for item in project_items if isinstance(item, dict) and item.get("type") == "file")
        directory_count = sum(1 for item in project_items if isinstance(item, dict) and item.get("type") == "directory")
        result["analysis_report"] = {
            "project_path": project_path,
            "items_total": len(project_items),
            "file_count": file_count,
            "directory_count": directory_count,
            "read_file_path": str(target),
            "read_file_lines": len(content.splitlines()),
            "read_file_chars": len(content),
        }
    return result


def filesystem_write_file(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    target = _resolve_workspace_path(workspace_root, params.get("path"))
    content = params.get("content")
    if not isinstance(content, str):
        raise ValueError("'content' must be a string.")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8-sig")
    return {
        "status": "success",
        "path": str(target),
        "bytes_written": len(content.encode("utf-8-sig")),
    }


def filesystem_list_directory(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    target = _resolve_workspace_path(workspace_root, params.get("path"))
    if not target.exists() or not target.is_dir():
        raise FileNotFoundError(f"Directory '{target}' does not exist.")

    items: list[dict[str, Any]] = []
    for child in sorted(target.iterdir(), key=lambda x: x.name.lower()):
        child_type = "directory" if child.is_dir() else "file"
        entry = {
            "name": child.name,
            "path": str(child),
            "type": child_type,
        }
        if child.is_file():
            entry["size_bytes"] = child.stat().st_size
        items.append(entry)

    return {
        "status": "success",
        "path": str(target),
        "project_path": str(target),
        "items": items,
    }


def execution_run_command(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    command = params.get("command")
    fallback_command = params.get("fallback_command")
    if not isinstance(command, str) or not command.strip():
        command = fallback_command
    if not isinstance(command, str) or not command.strip():
        raise ValueError("'command' must be a non-empty string.")
    command = command.strip()

    parts = shlex.split(command)
    if not parts:
        raise ValueError("'command' did not produce an executable token.")

    executable = parts[0]
    _assert_command_allowed(executable, tool_contract)

    cwd_param = params.get("cwd")
    if cwd_param is None:
        cwd = workspace_root.resolve()
    else:
        cwd = _resolve_workspace_path(workspace_root, cwd_param)

    timeout_ms = _tool_timeout_ms(tool_contract)
    try:
        completed = subprocess.run(
            parts,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=max(0.001, timeout_ms / 1000.0),
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"Command '{command}' exceeded timeout ({timeout_ms} ms).") from exc

    return {
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "exit_code": int(completed.returncode),
    }


def network_http_get(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    url = params.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("'url' must be a non-empty string.")

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("network_http_get only supports http/https URLs.")

    headers = params.get("headers")
    if headers is None:
        headers = {}
    if not isinstance(headers, dict):
        raise ValueError("'headers' must be an object when provided.")
    normalized_headers = {str(k): str(v) for k, v in headers.items()}

    timeout_ms = _tool_timeout_ms(tool_contract)
    request = Request(url, headers=normalized_headers, method="GET")

    try:
        with urlopen(request, timeout=max(0.001, timeout_ms / 1000.0)) as response:
            body_bytes = response.read()
            encoding = response.headers.get_content_charset() or "utf-8"
            return {
                "body": body_bytes.decode(encoding, errors="replace"),
                "status_code": int(response.status),
                "headers": {key: value for key, value in response.headers.items()},
            }
    except HTTPError as exc:
        body_bytes = exc.read()
        encoding = exc.headers.get_content_charset() if exc.headers else None
        return {
            "body": body_bytes.decode(encoding or "utf-8", errors="replace"),
            "status_code": int(exc.code),
            "headers": {key: value for key, value in (exc.headers.items() if exc.headers else [])},
        }
    except URLError as exc:
        raise ConnectionError(f"HTTP GET failed for '{url}': {exc.reason}") from exc


def _resolve_workspace_path(workspace_root: Path, path_value: Any) -> Path:
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError("A non-empty string 'path' is required.")
    path_value = path_value.strip()

    root = workspace_root.resolve()
    raw_path = Path(path_value)
    candidate = raw_path if raw_path.is_absolute() else (root / raw_path)
    resolved = candidate.resolve()

    try:
        common = os.path.commonpath([str(root), str(resolved)])
    except ValueError as exc:
        raise ToolSecurityError(f"Path '{path_value}' is outside allowed workspace.") from exc

    if Path(common) != root:
        raise ToolSecurityError(f"Path '{path_value}' is outside allowed workspace.")
    return resolved


def _tool_timeout_ms(tool_contract: dict[str, Any]) -> int:
    timeout_ms = int(tool_contract.get("constraints", {}).get("timeout_ms", 30000))
    return max(1, timeout_ms)


def _assert_command_allowed(executable: str, tool_contract: dict[str, Any]) -> None:
    if "/" in executable or "\\" in executable:
        raise ToolSecurityError("Executable must be a bare command name, not a path.")

    allowlist = tool_contract.get("constraints", {}).get("allowlist", [])
    normalized_allowlist = {_normalize_command_name(item) for item in allowlist if isinstance(item, str)}
    normalized_exec = _normalize_command_name(executable)

    if normalized_exec not in normalized_allowlist:
        raise ToolSecurityError(f"Command '{executable}' is not allowed.")


def _normalize_command_name(command: str) -> str:
    name = Path(command).name.strip().lower()
    for suffix in (".exe", ".cmd", ".bat"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name
