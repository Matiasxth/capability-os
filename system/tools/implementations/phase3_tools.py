from __future__ import annotations

import html as _html_module
import json
import os
import platform
import re
import shlex
import shutil
import signal
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class ToolSecurityError(PermissionError):
    """Raised when a tool violates workspace or command security constraints."""


# Optional workspace-aware path validator (set by phase3_registration if available)
_path_validator = None


def set_path_validator(validator) -> None:
    """Called by registration to enable workspace-aware validation."""
    global _path_validator
    _path_validator = validator



def filesystem_read_file(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    target = _resolve_workspace_path(workspace_root, params.get("path"), "read", "filesystem_read_file")
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
    target = _resolve_workspace_path(workspace_root, params.get("path"), "write", "filesystem_write_file")
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
    target = _resolve_workspace_path(workspace_root, params.get("path"), "read", "filesystem_list_directory")
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
        cwd = _resolve_workspace_path(workspace_root, cwd_param, "read", "execution_run_command")

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


# ---------------------------------------------------------------------------
# Filesystem — new tools (Bloque 1)
# ---------------------------------------------------------------------------

def filesystem_edit_file(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    target = _resolve_workspace_path(workspace_root, params.get("path"), "write", "filesystem_edit_file")
    if not target.exists() or not target.is_file():
        raise FileNotFoundError(f"File '{target}' does not exist.")

    new_string = params.get("new_string")
    if not isinstance(new_string, str):
        raise ValueError("'new_string' must be a string.")

    old_string = params.get("old_string")
    if old_string is None:
        # Full replacement mode
        content = new_string
    else:
        if not isinstance(old_string, str):
            raise ValueError("'old_string' must be a string when provided.")
        current = target.read_text(encoding="utf-8-sig")
        if old_string not in current:
            raise ValueError(f"'old_string' not found in file '{target}'.")
        content = current.replace(old_string, new_string, 1)

    target.write_text(content, encoding="utf-8-sig")
    return {
        "status": "success",
        "path": str(target),
        "bytes_written": len(content.encode("utf-8-sig")),
    }


def filesystem_copy_file(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    source = _resolve_workspace_path(workspace_root, params.get("source_path"), "read", "filesystem_copy_file")
    destination = _resolve_workspace_path(workspace_root, params.get("destination_path"), "write", "filesystem_copy_file")

    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Source file '{source}' does not exist.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source), str(destination))
    return {
        "status": "success",
        "source_path": str(source),
        "destination_path": str(destination),
    }


def filesystem_move_file(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    source = _resolve_workspace_path(workspace_root, params.get("source_path"), "write", "filesystem_move_file")
    destination = _resolve_workspace_path(workspace_root, params.get("destination_path"), "write", "filesystem_move_file")

    if not source.exists():
        raise FileNotFoundError(f"Source '{source}' does not exist.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return {
        "status": "success",
        "source_path": str(source),
        "destination_path": str(destination),
    }


def filesystem_delete_file(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    target = _resolve_workspace_path(workspace_root, params.get("path"), "write", "filesystem_delete_file")
    if not target.exists():
        raise FileNotFoundError(f"File '{target}' does not exist.")
    if not target.is_file():
        raise ValueError(f"'{target}' is not a file (directories not supported by this tool).")

    target.unlink()
    return {
        "status": "success",
        "path": str(target),
    }


# ---------------------------------------------------------------------------
# Execution — new tools (Bloque 1)
# ---------------------------------------------------------------------------

def execution_run_script(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    script_path_raw = params.get("script_path")
    script = _resolve_workspace_path(workspace_root, script_path_raw, "read", "execution_run_script")
    if not script.exists() or not script.is_file():
        raise FileNotFoundError(f"Script '{script}' does not exist.")

    args = params.get("args") or []
    if not isinstance(args, list):
        raise ValueError("'args' must be an array when provided.")

    # Determine interpreter from extension
    suffix = script.suffix.lower()
    if suffix == ".py":
        interpreter = sys.executable
    elif suffix in {".sh", ".bash"}:
        interpreter = "sh"
    else:
        interpreter = sys.executable  # default to python

    _assert_command_allowed(Path(interpreter).name, tool_contract)

    cwd_param = params.get("cwd")
    cwd = _resolve_workspace_path(workspace_root, cwd_param, "read", "execution_run_script") if cwd_param else workspace_root.resolve()

    timeout_ms = _tool_timeout_ms(tool_contract)
    cmd = [interpreter, str(script)] + [str(a) for a in args]
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=max(0.001, timeout_ms / 1000.0),
            shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"Script '{script_path_raw}' exceeded timeout ({timeout_ms} ms).") from exc

    return {
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "exit_code": int(completed.returncode),
    }


def execution_list_processes(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    name_filter = params.get("filter")
    if name_filter is not None and not isinstance(name_filter, str):
        raise ValueError("'filter' must be a string when provided.")

    processes: list[dict[str, Any]] = []
    try:
        import psutil  # type: ignore
        for proc in psutil.process_iter(["pid", "name", "status"]):
            try:
                info = proc.info
                if name_filter and name_filter.lower() not in (info.get("name") or "").lower():
                    continue
                processes.append({
                    "pid": info["pid"],
                    "name": info.get("name", ""),
                    "status": info.get("status", ""),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except ImportError:
        # Fallback: use tasklist (Windows) or ps (Unix) via subprocess
        processes = _list_processes_fallback(name_filter)

    return {"processes": processes, "count": len(processes)}


def execution_terminate_process(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    pid = params.get("process_id")
    if not isinstance(pid, int):
        raise ValueError("'process_id' must be an integer.")

    force = bool(params.get("force", False))

    try:
        if os.name == "nt":
            sig = signal.SIGTERM  # Windows only has SIGTERM via os.kill
            os.kill(pid, signal.SIGTERM)
        else:
            sig = signal.SIGKILL if force else signal.SIGTERM
            os.kill(pid, sig)
        status = "terminated"
    except ProcessLookupError:
        raise ValueError(f"No process with PID {pid} found.")
    except PermissionError as exc:
        raise PermissionError(f"Insufficient permissions to terminate PID {pid}.") from exc

    return {"status": status, "process_id": pid}


def execution_read_process_output(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    pid = params.get("process_id")
    if not isinstance(pid, int):
        raise ValueError("'process_id' must be an integer.")

    # Check if PID is alive
    running = False
    exit_code = None
    try:
        os.kill(pid, 0)
        running = True
    except ProcessLookupError:
        running = False
    except PermissionError:
        running = True  # Exists but we can't signal it
    except OSError:
        # Windows raises OSError for invalid PIDs (e.g. WinError 87)
        running = False

    return {
        "stdout": "",
        "stderr": "",
        "running": running,
        "exit_code": exit_code,
    }


# ---------------------------------------------------------------------------
# Network — new tools (Bloque 1)
# ---------------------------------------------------------------------------

def network_http_post(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    url = params.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("'url' must be a non-empty string.")

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("network_http_post only supports http/https URLs.")

    headers = dict(params.get("headers") or {})
    if not isinstance(headers, dict):
        raise ValueError("'headers' must be an object when provided.")
    normalized_headers = {str(k): str(v) for k, v in headers.items()}

    body_obj = params.get("body")
    body_text = params.get("body_text")

    if body_obj is not None:
        raw_body = json.dumps(body_obj).encode("utf-8")
        normalized_headers.setdefault("Content-Type", "application/json")
    elif isinstance(body_text, str):
        raw_body = body_text.encode("utf-8")
        normalized_headers.setdefault("Content-Type", "text/plain")
    else:
        raw_body = b""

    timeout_ms = _tool_timeout_ms(tool_contract)
    request = Request(url, data=raw_body, headers=normalized_headers, method="POST")

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
        raise ConnectionError(f"HTTP POST failed for '{url}': {exc.reason}") from exc


# ---------------------------------------------------------------------------
# System tools (Bloque 1)
# ---------------------------------------------------------------------------

def system_get_os_info(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    return {
        "platform": platform.system(),
        "platform_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": sys.version,
        "hostname": platform.node(),
    }


def system_get_env_var(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    name = params.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("'name' must be a non-empty string.")
    default = params.get("default")
    value = os.environ.get(name)
    if value is None:
        return {"name": name, "value": default, "found": False}
    return {"name": name, "value": value, "found": True}


def system_get_workspace_info(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    root = workspace_root.resolve()
    # Contracts live relative to this module: system/tools/implementations/ → project root is 3 levels up
    _module_dir = Path(__file__).resolve().parents[3]
    capabilities_path = _module_dir / "system" / "capabilities" / "contracts" / "v1"
    tools_path = _module_dir / "system" / "tools" / "contracts" / "v1"

    cap_count = len(list(capabilities_path.glob("*.json"))) if capabilities_path.exists() else 0
    tool_count = len(list(tools_path.glob("*.json"))) if tools_path.exists() else 0

    artifacts_path = str(root / "artifacts")
    sequences_path = str(root / "sequences")

    return {
        "workspace_root": str(root),
        "artifacts_path": artifacts_path,
        "sequences_path": sequences_path,
        "capabilities_count": cap_count,
        "tools_count": tool_count,
    }


# ---------------------------------------------------------------------------
# Network — HTML parsing tools (Bloque 2)
# ---------------------------------------------------------------------------

class _HTMLDocumentParser(HTMLParser):
    """Minimal stdlib HTML parser that collects title, links and text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._title_active = False
        self._tag_count = 0
        self.title: str = ""
        self.links: list[dict[str, str]] = []
        self._text_parts: list[str] = []
        self._current_a_text: list[str] = []
        self._in_a = False
        self._current_href: str = ""
        self._skip_tags = {"script", "style", "noscript"}
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        self._tag_count += 1
        tag_lower = tag.lower()
        if tag_lower in self._skip_tags:
            self._skip_depth += 1
        if tag_lower == "title":
            self._title_active = True
        if tag_lower == "a":
            self._in_a = True
            self._current_a_text = []
            href = dict(attrs).get("href", "")
            self._current_href = href or ""

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in self._skip_tags:
            self._skip_depth = max(0, self._skip_depth - 1)
        if tag_lower == "title":
            self._title_active = False
        if tag_lower == "a" and self._in_a:
            link_text = "".join(self._current_a_text).strip()
            if self._current_href:
                self.links.append({"text": link_text, "href": self._current_href})
            self._in_a = False
            self._current_a_text = []
            self._current_href = ""

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._title_active:
            self.title += data
        if self._in_a:
            self._current_a_text.append(data)
        text = data.strip()
        if text:
            self._text_parts.append(text)

    @property
    def text(self) -> str:
        return " ".join(self._text_parts)

    @property
    def tag_count(self) -> int:
        return self._tag_count


def network_parse_html(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    html = params.get("html")
    if not isinstance(html, str):
        raise ValueError("'html' must be a string.")

    parser = _HTMLDocumentParser()
    parser.feed(html)

    return {
        "title": parser.title.strip(),
        "text": parser.text,
        "links": parser.links,
        "tag_count": parser.tag_count,
    }


def network_extract_links(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    document = params.get("document")
    if not isinstance(document, dict):
        raise ValueError("'document' must be a parsed HTML document object.")

    links = document.get("links", [])
    if not isinstance(links, list):
        links = []

    return {"links": links, "count": len(links)}


def network_extract_text(params: dict[str, Any], tool_contract: dict[str, Any], workspace_root: Path) -> dict[str, Any]:
    document = params.get("document")
    if not isinstance(document, dict):
        raise ValueError("'document' must be a parsed HTML document object.")

    text = document.get("text", "")
    if not isinstance(text, str):
        text = ""

    words = text.split()
    return {"text": text, "word_count": len(words)}


# ---------------------------------------------------------------------------
# Private helpers for new tools
# ---------------------------------------------------------------------------

def _list_processes_fallback(name_filter: str | None) -> list[dict[str, Any]]:
    """Fallback process listing without psutil."""
    processes: list[dict[str, Any]] = []
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["tasklist", "/fo", "csv", "/nh"],
                capture_output=True, text=True, timeout=10, shell=False,
            )
            for line in result.stdout.splitlines():
                parts = [p.strip('"') for p in line.split('","')]
                if len(parts) >= 2:
                    pname = parts[0]
                    try:
                        ppid = int(parts[1])
                    except ValueError:
                        ppid = 0
                    if name_filter and name_filter.lower() not in pname.lower():
                        continue
                    processes.append({"pid": ppid, "name": pname, "status": "unknown"})
        else:
            result = subprocess.run(
                ["ps", "-eo", "pid,comm,stat"],
                capture_output=True, text=True, timeout=10, shell=False,
            )
            for line in result.stdout.splitlines()[1:]:
                parts = line.split(None, 2)
                if len(parts) >= 2:
                    try:
                        ppid = int(parts[0])
                    except ValueError:
                        continue
                    pname = parts[1]
                    pstatus = parts[2].strip() if len(parts) > 2 else "unknown"
                    if name_filter and name_filter.lower() not in pname.lower():
                        continue
                    processes.append({"pid": ppid, "name": pname, "status": pstatus})
    except Exception:
        pass
    return processes


def _resolve_workspace_path(workspace_root: Path, path_value: Any, operation: str = "read", capability_id: str | None = None) -> Path:
    if not isinstance(path_value, str) or not path_value.strip():
        raise ValueError("A non-empty string 'path' is required.")
    path_value = path_value.strip()

    root = workspace_root.resolve()
    raw_path = Path(path_value)
    candidate = raw_path if raw_path.is_absolute() else (root / raw_path)
    resolved = candidate.resolve()

    # New system: delegate to PathValidator when available
    if _path_validator is not None:
        try:
            result = _path_validator.validate(str(resolved), operation, capability_id=capability_id)
            if result["allowed"]:
                # Path is inside a registered workspace and access is granted
                return resolved
            if result["workspace"] is not None:
                # A workspace matched but denied access (read-only, inactive, etc.)
                raise ToolSecurityError(f"Workspace access denied: {result['reason']}")
            # No workspace matched → fall through to legacy workspace_root check
        except ToolSecurityError:
            raise
        except Exception:
            pass  # Validator error → don't block (Rule 5)

    # Legacy system: restrict to workspace_root only
    try:
        root_s = str(root)
        resolved_s = str(resolved)
        if os.name == "nt":
            root_s = root_s.lower()
            resolved_s = resolved_s.lower()
        common = os.path.commonpath([root_s, resolved_s])
    except ValueError as exc:
        raise ToolSecurityError(f"Path '{path_value}' is outside allowed workspace.") from exc

    if common != root_s:
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
