"""Skill manifest validation.

A skill is an installable package containing capability contracts,
tool contracts, and optional tool implementations.

Manifest format (.capos-skill.json):
{
  "id": "my-skill",
  "name": "My Skill",
  "version": "1.0.0",
  "author": "developer",
  "description": "What this skill does",
  "capabilities": [
    {"contract": "capabilities/my_cap.json"}
  ],
  "tools": [
    {"id": "my_tool", "contract": "tools/my_tool.json", "implementation": "tools/my_tool.py"}
  ],
  "dependencies": {"python": [], "system": []}
}
"""
from __future__ import annotations

from typing import Any


REQUIRED_FIELDS = {"id", "name", "version", "description"}


class SkillManifestError(ValueError):
    """Raised when a skill manifest is invalid."""


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """Validate a skill manifest dict. Returns list of error strings (empty = valid)."""
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        val = manifest.get(field)
        if not isinstance(val, str) or not val.strip():
            errors.append(f"Missing or empty required field: '{field}'")

    # Version format (loose semver)
    version = manifest.get("version", "")
    if isinstance(version, str) and version.count(".") < 1:
        errors.append(f"Version '{version}' should be semver (e.g., '1.0.0')")

    capabilities = manifest.get("capabilities", [])
    if not isinstance(capabilities, list):
        errors.append("'capabilities' must be a list")
    else:
        for i, cap in enumerate(capabilities):
            if not isinstance(cap, dict) or not cap.get("contract"):
                errors.append(f"capabilities[{i}]: missing 'contract' path")

    tools = manifest.get("tools", [])
    if not isinstance(tools, list):
        errors.append("'tools' must be a list")
    else:
        for i, tool in enumerate(tools):
            if not isinstance(tool, dict):
                errors.append(f"tools[{i}]: must be an object")
                continue
            if not tool.get("id"):
                errors.append(f"tools[{i}]: missing 'id'")
            if not tool.get("contract"):
                errors.append(f"tools[{i}]: missing 'contract' path")

    return errors
