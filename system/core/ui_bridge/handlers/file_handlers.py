"""File API handlers: tree, read, write, create, delete, rename, terminal."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


def _resp(code, data):
    return type("R", (), {"status_code": code.value, "payload": data})()


def _err(code, error_code, msg):
    raise type("E", (Exception,), {"status_code": code.value, "error_code": error_code, "error_message": msg, "details": {}})()


def file_tree(service: Any, payload: Any, ws_id: str = "", _raw_path: str = "", **kw: Any):
    """Get file tree of a workspace."""
    ws = service.workspace_registry.get(ws_id) if ws_id else service.workspace_registry.get_default()
    if ws is None:
        # Use project root as fallback
        root = service.project_root
    else:
        root = Path(ws["path"])

    qs = parse_qs(urlparse(_raw_path).query) if _raw_path else {}
    rel = qs.get("path", ["."])[0]
    target = (root / rel).resolve()

    if not target.exists():
        return _resp(HTTPStatus.NOT_FOUND, {"error": "Path not found"})

    def scan(p: Path, depth: int = 0) -> list[dict]:
        if depth > 3:
            return []
        items = []
        try:
            for entry in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if entry.name.startswith(".") and entry.name not in (".env", ".gitignore"):
                    continue
                if entry.name in ("node_modules", "__pycache__", ".git", "dist", "venv"):
                    continue
                item: dict[str, Any] = {
                    "name": entry.name,
                    "path": str(entry.relative_to(root)),
                    "type": "directory" if entry.is_dir() else "file",
                }
                if entry.is_file():
                    try:
                        item["size"] = entry.stat().st_size
                    except Exception:
                        item["size"] = 0
                    item["ext"] = entry.suffix.lstrip(".")
                if entry.is_dir() and depth < 2:
                    item["children"] = scan(entry, depth + 1)
                items.append(item)
        except PermissionError:
            pass
        return items

    tree = scan(target)
    return _resp(HTTPStatus.OK, {"root": str(root), "path": rel, "items": tree})


def file_read(service: Any, payload: Any, **kw: Any):
    """Read file content."""
    qs = parse_qs(urlparse(kw.get("_raw_path", "")).query)
    path = qs.get("path", [""])[0]
    ws_id = qs.get("ws", [""])[0]

    ws = service.workspace_registry.get(ws_id) if ws_id else service.workspace_registry.get_default()
    root = Path(ws["path"]) if ws else service.project_root

    file_path = (root / path).resolve()
    if not file_path.exists():
        return _resp(HTTPStatus.NOT_FOUND, {"error": f"File not found: {path}"})
    if not file_path.is_file():
        return _resp(HTTPStatus.BAD_REQUEST, {"error": "Not a file"})
    if file_path.stat().st_size > 2_000_000:
        return _resp(HTTPStatus.BAD_REQUEST, {"error": "File too large (>2MB)"})

    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return _resp(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    # Detect language from extension
    ext_lang = {
        "py": "python", "js": "javascript", "jsx": "javascript", "ts": "typescript",
        "tsx": "typescript", "json": "json", "md": "markdown", "html": "html",
        "css": "css", "yml": "yaml", "yaml": "yaml", "sh": "shell",
        "sql": "sql", "xml": "xml", "txt": "plaintext",
    }
    ext = file_path.suffix.lstrip(".")
    language = ext_lang.get(ext, "plaintext")

    return _resp(HTTPStatus.OK, {
        "path": path,
        "content": content,
        "language": language,
        "size": len(content),
        "encoding": "utf-8",
    })


def file_write(service: Any, payload: Any, **kw: Any):
    """Write file content (Level 2 — should have confirmation)."""
    p = payload or {}
    path = p.get("path", "")
    content = p.get("content", "")
    ws_id = p.get("ws_id", "")

    ws = service.workspace_registry.get(ws_id) if ws_id else service.workspace_registry.get_default()
    root = Path(ws["path"]) if ws else service.project_root

    file_path = (root / path).resolve()

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return _resp(HTTPStatus.OK, {"status": "success", "path": path, "size": len(content)})
    except Exception as exc:
        return _resp(HTTPStatus.INTERNAL_SERVER_ERROR, {"status": "error", "error": str(exc)})


def file_create(service: Any, payload: Any, **kw: Any):
    """Create a new file or directory."""
    p = payload or {}
    path = p.get("path", "")
    is_dir = p.get("is_directory", False)
    ws_id = p.get("ws_id", "")

    ws = service.workspace_registry.get(ws_id) if ws_id else service.workspace_registry.get_default()
    root = Path(ws["path"]) if ws else service.project_root
    target = (root / path).resolve()

    try:
        if is_dir:
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("", encoding="utf-8")
        return _resp(HTTPStatus.CREATED, {"status": "success", "path": path, "type": "directory" if is_dir else "file"})
    except Exception as exc:
        return _resp(HTTPStatus.INTERNAL_SERVER_ERROR, {"status": "error", "error": str(exc)})


def file_delete(service: Any, payload: Any, **kw: Any):
    """Delete a file or directory."""
    qs = parse_qs(urlparse(kw.get("_raw_path", "")).query)
    path = qs.get("path", [""])[0]
    ws_id = qs.get("ws", [""])[0]

    ws = service.workspace_registry.get(ws_id) if ws_id else service.workspace_registry.get_default()
    root = Path(ws["path"]) if ws else service.project_root
    target = (root / path).resolve()

    if not target.exists():
        return _resp(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    try:
        import shutil
        if target.is_dir():
            shutil.rmtree(str(target))
        else:
            target.unlink()
        return _resp(HTTPStatus.OK, {"status": "success", "deleted": path})
    except Exception as exc:
        return _resp(HTTPStatus.INTERNAL_SERVER_ERROR, {"status": "error", "error": str(exc)})


def workspace_analyze(service: Any, payload: Any, ws_id: str = "", **kw: Any):
    """Analyze workspace for issues and suggestions."""
    ws = service.workspace_registry.get(ws_id) if ws_id else service.workspace_registry.get_default()
    if ws is None:
        return _resp(HTTPStatus.NOT_FOUND, {"error": "Workspace not found"})
    from system.core.supervisor.workspace_monitor import WorkspaceMonitor
    return _resp(HTTPStatus.OK, WorkspaceMonitor().analyze(ws["path"]))


def workspace_auto_clean(service: Any, payload: Any, ws_id: str = "", **kw: Any):
    """Auto-clean workspace. dry_run=true by default."""
    ws = service.workspace_registry.get(ws_id) if ws_id else service.workspace_registry.get_default()
    if ws is None:
        return _resp(HTTPStatus.NOT_FOUND, {"error": "Workspace not found"})
    dry_run = (payload or {}).get("dry_run", True)
    from system.core.supervisor.workspace_monitor import WorkspaceMonitor
    return _resp(HTTPStatus.OK, WorkspaceMonitor().auto_clean(ws["path"], dry_run=dry_run))


def workspace_generate_readme(service: Any, payload: Any, ws_id: str = "", **kw: Any):
    """Generate README via Claude."""
    ws = service.workspace_registry.get(ws_id) if ws_id else service.workspace_registry.get_default()
    if ws is None:
        return _resp(HTTPStatus.NOT_FOUND, {"error": "Workspace not found"})
    from system.core.supervisor.workspace_monitor import WorkspaceMonitor
    prompt = WorkspaceMonitor().generate_readme_prompt(ws["path"])
    if hasattr(service, "supervisor") and service.supervisor.claude_bridge.available:
        readme = service.supervisor.invoke_claude(prompt)
        return _resp(HTTPStatus.OK, {"status": "success", "readme": readme})
    return _resp(HTTPStatus.OK, {"status": "error", "error": "Claude not available", "prompt": prompt})


def workspace_suggest_structure(service: Any, payload: Any, **kw: Any):
    """Suggest project structure."""
    project_type = (payload or {}).get("type", "python")
    from system.core.supervisor.workspace_monitor import WorkspaceMonitor
    return _resp(HTTPStatus.OK, WorkspaceMonitor().suggest_structure(project_type))


def file_terminal(service: Any, payload: Any, **kw: Any):
    """Execute a command in the workspace directory."""
    p = payload or {}
    command = p.get("command", "")
    ws_id = p.get("ws_id", "")

    if not command.strip():
        return _resp(HTTPStatus.BAD_REQUEST, {"error": "Command required"})

    ws = service.workspace_registry.get(ws_id) if ws_id else service.workspace_registry.get_default()
    cwd = Path(ws["path"]) if ws else service.project_root

    try:
        result = subprocess.run(
            command, shell=True, cwd=str(cwd),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=30,
        )
        return _resp(HTTPStatus.OK, {
            "status": "success",
            "stdout": result.stdout[-5000:],
            "stderr": result.stderr[-2000:],
            "exit_code": result.returncode,
        })
    except subprocess.TimeoutExpired:
        return _resp(HTTPStatus.OK, {"status": "error", "error": "Command timed out (30s)"})
    except Exception as exc:
        return _resp(HTTPStatus.OK, {"status": "error", "error": str(exc)})
