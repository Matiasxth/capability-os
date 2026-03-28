"""Template engine for generating integration scaffolding (spec section 13.4 step 5).

Selects a base template per integration type and fills it with plan data.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any


_MANIFEST_TEMPLATES: dict[str, dict[str, Any]] = {
    "web_app": {
        "type": "web_app",
        "status": "not_configured",
        "requirements": {"browser": True},
        "lifecycle": {"version": "0.1.0"},
    },
    "rest_api": {
        "type": "rest_api",
        "status": "not_configured",
        "requirements": {"auth": "api_key"},
        "lifecycle": {"version": "0.1.0"},
    },
    "local_app": {
        "type": "local_app",
        "status": "not_configured",
        "requirements": {"executable": True},
        "lifecycle": {"version": "0.1.0"},
    },
    "file_based": {
        "type": "file_based",
        "status": "not_configured",
        "requirements": {"workspace_access": True},
        "lifecycle": {"version": "0.1.0"},
    },
}

_DIRECTORY_SKELETON = [
    "capabilities",
    "tools",
    "config",
    "tests",
]


class TemplateEngine:
    """Renders integration manifests and directory structures from plans."""

    def render_manifest(self, plan: dict[str, Any]) -> dict[str, Any]:
        integration_type = plan.get("integration_type", "rest_api")
        template = deepcopy(_MANIFEST_TEMPLATES.get(integration_type, _MANIFEST_TEMPLATES["rest_api"]))

        manifest: dict[str, Any] = {
            "id": plan.get("integration_id", "unknown_connector"),
            "name": plan.get("integration_id", "unknown_connector").replace("_", " ").title(),
            **template,
            "capabilities": list(plan.get("capabilities", [])),
        }
        # Override requirements if plan specifies them
        plan_reqs = plan.get("requirements")
        if isinstance(plan_reqs, dict) and plan_reqs:
            manifest["requirements"] = deepcopy(plan_reqs)

        return manifest

    def render_directory_list(self, plan: dict[str, Any]) -> list[str]:
        """Return relative directory paths that should be created for the integration."""
        integration_id = plan.get("integration_id", "unknown_connector")
        base = f"{integration_id}"
        dirs = [base]
        for sub in _DIRECTORY_SKELETON:
            dirs.append(f"{base}/{sub}")
        return dirs
