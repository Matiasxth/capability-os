"""Extended system tools: monitor, packages, git, backup.

These tools give the agent (and supervisor) control over the system:
- System monitoring (CPU, RAM, disk, processes)
- Package management (pip install/uninstall)
- Git operations (status, commit, push)
- Backup/restore of system state
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ═══════════════════════════════════════════════════════
# System Monitor
# ═══════════════════════════════════════════════════════

def system_monitor_overview(params: dict, contract: dict) -> dict[str, Any]:
    """Get system overview: OS, CPU, RAM, disk."""
    import platform
    info: dict[str, Any] = {
        "status": "success",
        "os": platform.system(),
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "hostname": platform.node(),
    }

    # Disk usage
    try:
        usage = shutil.disk_usage("/")
        info["disk"] = {
            "total_gb": round(usage.total / (1024**3), 1),
            "used_gb": round(usage.used / (1024**3), 1),
            "free_gb": round(usage.free / (1024**3), 1),
            "percent_used": round(usage.used / usage.total * 100, 1),
        }
    except Exception:
        pass

    # Process count
    try:
        if sys.platform == "win32":
            result = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=5)
            info["process_count"] = len(result.stdout.strip().splitlines()) - 3
        else:
            result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
            info["process_count"] = len(result.stdout.strip().splitlines()) - 1
    except Exception:
        pass

    return info


def system_monitor_processes(params: dict, contract: dict) -> dict[str, Any]:
    """List running processes with resource usage."""
    filter_name = params.get("filter", "")
    limit = min(params.get("limit", 20), 50)

    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
            )
            processes = []
            for line in result.stdout.strip().splitlines()[:100]:
                parts = line.strip('"').split('","')
                if len(parts) >= 5:
                    name = parts[0]
                    if filter_name and filter_name.lower() not in name.lower():
                        continue
                    processes.append({"name": name, "pid": parts[1], "memory": parts[4]})
        else:
            result = subprocess.run(
                ["ps", "aux", "--sort=-%mem"],
                capture_output=True, text=True, timeout=10,
            )
            processes = []
            for line in result.stdout.strip().splitlines()[1:100]:
                parts = line.split()
                if len(parts) >= 11:
                    name = parts[10]
                    if filter_name and filter_name.lower() not in name.lower():
                        continue
                    processes.append({"user": parts[0], "pid": parts[1], "cpu": parts[2], "mem": parts[3], "command": " ".join(parts[10:])})

        return {"status": "success", "processes": processes[:limit], "total": len(processes)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


# ═══════════════════════════════════════════════════════
# Package Manager
# ═══════════════════════════════════════════════════════

def package_install(params: dict, contract: dict) -> dict[str, Any]:
    """Install a pip package."""
    package = params.get("package", "").strip()
    if not package:
        return {"status": "error", "error": "Package name required"}
    # Security: block dangerous packages
    dangerous = {"os", "sys", "subprocess", "shutil", "ctypes"}
    if package.lower() in dangerous:
        return {"status": "error", "error": f"Package '{package}' is blocked for security"}

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", package],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
        return {
            "status": "success" if result.returncode == 0 else "error",
            "package": package,
            "output": result.stdout[-500:] if result.stdout else "",
            "error": result.stderr[-300:] if result.returncode != 0 else "",
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "Installation timed out (120s)"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def package_list(params: dict, contract: dict) -> dict[str, Any]:
    """List installed pip packages."""
    filter_name = params.get("filter", "")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "list", "--format=json"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        packages = json.loads(result.stdout) if result.stdout else []
        if filter_name:
            packages = [p for p in packages if filter_name.lower() in p.get("name", "").lower()]
        return {"status": "success", "packages": packages[:50], "total": len(packages)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


# ═══════════════════════════════════════════════════════
# Git Operations
# ═══════════════════════════════════════════════════════

def git_status(params: dict, contract: dict) -> dict[str, Any]:
    """Get git status of the workspace."""
    path = params.get("path", ".")
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "-b"],
            cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        )
        lines = result.stdout.strip().splitlines()
        branch = lines[0].replace("## ", "") if lines else "unknown"
        changes = [{"status": l[:2].strip(), "file": l[3:]} for l in lines[1:] if l.strip()]
        return {"status": "success", "branch": branch, "changes": changes[:30], "total_changes": len(changes)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def git_log(params: dict, contract: dict) -> dict[str, Any]:
    """Get recent git log."""
    path = params.get("path", ".")
    limit = min(params.get("limit", 10), 30)
    try:
        result = subprocess.run(
            ["git", "log", f"--oneline", f"-{limit}"],
            cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
        )
        commits = []
        for line in result.stdout.strip().splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                commits.append({"hash": parts[0], "message": parts[1]})
        return {"status": "success", "commits": commits}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def git_commit(params: dict, contract: dict) -> dict[str, Any]:
    """Create a git commit."""
    message = params.get("message", "").strip()
    path = params.get("path", ".")
    if not message:
        return {"status": "error", "error": "Commit message required"}
    try:
        # Stage all changes
        subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True, timeout=10)
        result = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=path, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        )
        return {
            "status": "success" if result.returncode == 0 else "error",
            "output": result.stdout[-300:],
            "error": result.stderr[-200:] if result.returncode != 0 else "",
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


# ═══════════════════════════════════════════════════════
# Backup
# ═══════════════════════════════════════════════════════

def backup_create(params: dict, contract: dict) -> dict[str, Any]:
    """Create a backup of system state (settings, agents, workspaces, memory)."""
    workspace = params.get("workspace_root", "C:/data/workspace")
    ws_path = Path(workspace)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = ws_path / "backups" / timestamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    files_backed = []
    for name in ["memory/history.json", "agents.json", "workspaces.json", "queue.json"]:
        src = ws_path / name
        if src.exists():
            dst = backup_dir / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            files_backed.append(name)

    # Settings
    for settings_path in [Path("system/settings.json"), Path("system/settings.example.json")]:
        if settings_path.exists():
            dst = backup_dir / settings_path.name
            shutil.copy2(str(settings_path), str(dst))
            files_backed.append(str(settings_path))

    return {
        "status": "success",
        "backup_path": str(backup_dir),
        "files": files_backed,
        "timestamp": timestamp,
    }


def backup_list(params: dict, contract: dict) -> dict[str, Any]:
    """List available backups."""
    workspace = params.get("workspace_root", "C:/data/workspace")
    backup_root = Path(workspace) / "backups"
    if not backup_root.exists():
        return {"status": "success", "backups": []}

    backups = []
    for d in sorted(backup_root.iterdir(), reverse=True):
        if d.is_dir():
            files = list(d.rglob("*"))
            backups.append({
                "name": d.name,
                "path": str(d),
                "files": len([f for f in files if f.is_file()]),
                "size_bytes": sum(f.stat().st_size for f in files if f.is_file()),
            })
    return {"status": "success", "backups": backups[:20]}
