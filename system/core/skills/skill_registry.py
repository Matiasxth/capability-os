"""Skill Registry — install, uninstall, list installable skill packages.

A "skill" is a directory containing:
  - capos-skill.json (manifest)
  - capabilities/*.json (capability contracts)
  - tools/*.json + tools/*.py (tool contracts + implementations)

Skills are installed to workspace/skills/<skill_id>/.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from threading import RLock
from typing import Any

from .skill_manifest import SkillManifestError, validate_manifest


class SkillRegistry:
    """Manages installed skills with capability and tool registration."""

    def __init__(
        self,
        skills_dir: Path,
        capability_registry: Any = None,
        tool_registry: Any = None,
        tool_runtime: Any = None,
    ):
        self._skills_dir = Path(skills_dir).resolve()
        self._skills_dir.mkdir(parents=True, exist_ok=True)
        self._capability_registry = capability_registry
        self._tool_registry = tool_registry
        self._tool_runtime = tool_runtime
        self._lock = RLock()
        self._installed: dict[str, dict[str, Any]] = {}  # skill_id → manifest
        self._state_file = self._skills_dir / "skills_data.json"

    def load_installed(self) -> None:
        """Load and re-register all installed skills from disk."""
        if self._state_file.exists():
            try:
                data = json.loads(self._state_file.read_text(encoding="utf-8"))
                self._installed = data.get("skills", {})
            except (json.JSONDecodeError, OSError):
                self._installed = {}
        # Re-register capabilities and tools
        for skill_id, manifest in list(self._installed.items()):
            skill_path = self._skills_dir / skill_id
            if not skill_path.is_dir():
                del self._installed[skill_id]
                continue
            self._register_skill_assets(skill_id, manifest, skill_path)
        self._save_state()

    def install_from_path(self, source_path: str | Path) -> dict[str, Any]:
        """Install a skill from a local directory path. Returns the manifest."""
        src = Path(source_path).resolve()
        manifest_path = src / "capos-skill.json"
        if not manifest_path.exists():
            raise SkillManifestError(f"No capos-skill.json found in '{src}'")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        errors = validate_manifest(manifest)
        if errors:
            raise SkillManifestError(f"Invalid manifest: {'; '.join(errors)}")

        skill_id = manifest["id"]
        with self._lock:
            if skill_id in self._installed:
                raise SkillManifestError(f"Skill '{skill_id}' is already installed")
            dest = self._skills_dir / skill_id
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
            self._installed[skill_id] = manifest
            self._register_skill_assets(skill_id, manifest, dest)
            self._save_state()
        return manifest

    def uninstall(self, skill_id: str) -> bool:
        """Uninstall a skill by ID. Returns True if removed."""
        with self._lock:
            if skill_id not in self._installed:
                return False
            dest = self._skills_dir / skill_id
            if dest.exists():
                shutil.rmtree(dest)
            del self._installed[skill_id]
            self._save_state()
        return True

    def list_installed(self) -> list[dict[str, Any]]:
        """Return all installed skill manifests."""
        with self._lock:
            return [
                {"id": sid, **{k: v for k, v in m.items() if k != "id"}}
                for sid, m in self._installed.items()
            ]

    def get_skill(self, skill_id: str) -> dict[str, Any] | None:
        """Return a single skill manifest or None."""
        with self._lock:
            m = self._installed.get(skill_id)
            return dict(m) if m else None

    # ── Internal ──

    def _register_skill_assets(self, skill_id: str, manifest: dict[str, Any], skill_path: Path) -> None:
        """Register capability and tool contracts from a skill."""
        # Register capabilities
        for cap_entry in manifest.get("capabilities", []):
            contract_rel = cap_entry.get("contract", "")
            contract_file = skill_path / contract_rel
            if contract_file.exists() and self._capability_registry is not None:
                try:
                    contract = json.loads(contract_file.read_text(encoding="utf-8"))
                    self._capability_registry.validate_contract(contract, source=f"skill:{skill_id}")
                except Exception:
                    pass

        # Register tool contracts
        for tool_entry in manifest.get("tools", []):
            contract_rel = tool_entry.get("contract", "")
            contract_file = skill_path / contract_rel
            if contract_file.exists() and self._tool_registry is not None:
                try:
                    contract = json.loads(contract_file.read_text(encoding="utf-8"))
                    self._tool_registry.register(contract)
                except Exception:
                    pass

            # Dynamic tool implementation loading
            impl_rel = tool_entry.get("implementation", "")
            tool_id = tool_entry.get("id", "")
            if impl_rel and tool_id and self._tool_runtime is not None:
                impl_file = skill_path / impl_rel
                if impl_file.exists():
                    try:
                        from .skill_loader import load_tool_handler
                        handler = load_tool_handler(impl_file, tool_id)
                        if handler:
                            self._tool_runtime.register_handler(tool_id, handler)
                    except Exception:
                        pass

    def _save_state(self) -> None:
        try:
            payload = {"skills": self._installed}
            self._state_file.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            pass
