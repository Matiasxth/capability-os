"""Creates the directory structure and manifest for a new integration (spec section 13.4 step 6).

Uses the Template Engine's output to write the actual files on disk
under the integrations installed directory.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from system.integrations.templates.template_engine import TemplateEngine


class IntegrationGeneratorError(RuntimeError):
    """Raised when integration generation fails."""


class IntegrationGenerator:
    """Generates integration scaffolding on disk."""

    def __init__(self, integrations_root: str | Path):
        self.integrations_root = Path(integrations_root).resolve()

    def generate(
        self,
        plan: dict[str, Any],
        manifest: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        template_engine = TemplateEngine()

        if manifest is None:
            manifest = template_engine.render_manifest(plan)

        integration_id = manifest.get("id", plan.get("integration_id", "unknown"))
        integration_dir = self.integrations_root / integration_id

        if integration_dir.exists():
            raise IntegrationGeneratorError(
                f"Integration directory '{integration_dir}' already exists."
            )

        # Create directories
        dirs = template_engine.render_directory_list(plan)
        for rel_dir in dirs:
            (self.integrations_root / rel_dir).mkdir(parents=True, exist_ok=True)

        # Write manifest
        manifest_path = integration_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        # Write empty __init__.py
        init_path = integration_dir / "__init__.py"
        init_path.write_text("", encoding="utf-8")

        return {
            "integration_id": integration_id,
            "path": str(integration_dir),
            "manifest_path": str(manifest_path),
            "directories_created": dirs,
            "status": "generated",
        }
