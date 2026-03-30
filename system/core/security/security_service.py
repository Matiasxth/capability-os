"""Progressive security classification for all tool/capability executions.

Three levels:
  Level 1 (FREE)      — Read-only, safe ops. No confirmation needed.
  Level 2 (CONFIRM)   — Write/modify within workspace. User clicks "Allow".
  Level 3 (PROTECTED) — System files, destructive ops. Password/2FA required.

Used by the Agent Loop, API handlers, and Channel Polling Workers.
"""
from __future__ import annotations

import json
import os
from enum import IntEnum
from pathlib import Path
from typing import Any


class SecurityLevel(IntEnum):
    FREE = 1
    CONFIRM = 2
    PROTECTED = 3


_RULES_PATH = Path(__file__).resolve().parent / "security_rules.json"


class SecurityService:
    """Classifies operations into security levels."""

    def __init__(self, workspace_roots: list[str | Path] | None = None) -> None:
        self._workspace_roots: list[Path] = [Path(w).resolve() for w in (workspace_roots or [])]
        self._rules = self._load_rules()
        self._free_tools: set[str] = set(self._rules.get("free", {}).get("tools", []))
        self._free_caps: set[str] = set(self._rules.get("free", {}).get("capabilities", []))
        self._confirm_tools: set[str] = set(self._rules.get("confirm", {}).get("tools", []))
        self._confirm_caps: set[str] = set(self._rules.get("confirm", {}).get("capabilities", []))
        self._protected_tools: set[str] = set(self._rules.get("protected", {}).get("tools", []))
        self._protected_caps: set[str] = set(self._rules.get("protected", {}).get("capabilities", []))
        self._critical_patterns: list[str] = self._rules.get("critical_paths", {}).get("patterns", [])

    def add_workspace(self, path: str | Path) -> None:
        resolved = Path(path).resolve()
        if resolved not in self._workspace_roots:
            self._workspace_roots.append(resolved)

    def classify(
        self,
        capability_id: str = "",
        tool_id: str = "",
        inputs: dict[str, Any] | None = None,
    ) -> SecurityLevel:
        """Classify an operation into a security level.

        Checks in order: critical paths → protected → confirm → free.
        Default is CONFIRM (safe fallback).
        """
        inputs = inputs or {}

        # Check if any input path touches a critical location
        path_level = self._check_paths(inputs)
        if path_level == SecurityLevel.PROTECTED:
            return SecurityLevel.PROTECTED

        # Check explicit protected rules
        if tool_id in self._protected_tools or capability_id in self._protected_caps:
            return SecurityLevel.PROTECTED

        # Check if write operation targets path outside ALL workspaces
        if self._is_write_outside_workspace(tool_id, capability_id, inputs):
            return SecurityLevel.PROTECTED

        # Check explicit free rules
        if tool_id in self._free_tools or capability_id in self._free_caps:
            return SecurityLevel.FREE

        # Check explicit confirm rules
        if tool_id in self._confirm_tools or capability_id in self._confirm_caps:
            return SecurityLevel.CONFIRM

        # Default: CONFIRM (require approval for unknown operations)
        return SecurityLevel.CONFIRM

    def classify_description(self, level: SecurityLevel) -> str:
        """Human-readable description of a security level."""
        descriptions = {
            SecurityLevel.FREE: "Safe operation — no confirmation needed",
            SecurityLevel.CONFIRM: "This action modifies files or runs commands — confirmation required",
            SecurityLevel.PROTECTED: "Critical operation — password authentication required",
        }
        return descriptions.get(level, "Unknown security level")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _check_paths(self, inputs: dict[str, Any]) -> SecurityLevel | None:
        """Check if any path-like input touches a critical location."""
        path_fields = ("path", "file_path", "source", "destination", "directory", "target")
        for field in path_fields:
            value = inputs.get(field)
            if not isinstance(value, str) or not value.strip():
                continue
            normalized = value.replace("/", os.sep).replace("\\", os.sep).lower()
            for pattern in self._critical_patterns:
                if pattern.lower() in normalized:
                    return SecurityLevel.PROTECTED
        # Also check the 'command' field for dangerous commands
        command = inputs.get("command", "")
        if isinstance(command, str):
            cmd_lower = command.lower().strip()
            dangerous = ("rm -rf", "del /s", "format", "shutdown", "reboot", "mkfs", "fdisk", "registry")
            for d in dangerous:
                if d in cmd_lower:
                    return SecurityLevel.PROTECTED
        return None

    def _is_write_outside_workspace(
        self, tool_id: str, capability_id: str, inputs: dict[str, Any]
    ) -> bool:
        """Check if a write-like operation targets a path outside all workspaces."""
        write_tools = {
            "filesystem_write_file", "filesystem_delete_file", "filesystem_delete_directory",
            "filesystem_move_file", "filesystem_copy_file", "filesystem_create_directory",
        }
        write_caps = {
            "write_file", "edit_file", "delete_file", "delete_directory",
            "move_file", "copy_file", "create_directory",
        }
        if tool_id not in write_tools and capability_id not in write_caps:
            return False

        if not self._workspace_roots:
            return False  # No workspaces configured — can't determine

        path_fields = ("path", "file_path", "source", "destination", "directory", "target")
        for field in path_fields:
            value = inputs.get(field)
            if not isinstance(value, str) or not value.strip():
                continue
            try:
                resolved = Path(value).resolve()
                inside = any(
                    self._is_subpath(resolved, ws) for ws in self._workspace_roots
                )
                if not inside:
                    return True
            except Exception:
                return True  # Can't resolve path — treat as outside
        return False

    @staticmethod
    def _is_subpath(child: Path, parent: Path) -> bool:
        try:
            child.relative_to(parent)
            return True
        except ValueError:
            return False

    @staticmethod
    def _load_rules() -> dict[str, Any]:
        try:
            return json.loads(_RULES_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
