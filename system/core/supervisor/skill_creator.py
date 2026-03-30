"""Skill Creator — generates and hot-loads new tools without server restart.

Creates tool contract JSON + Python handler, registers them in the running
ToolRegistry and ToolRuntime, and updates the AgentLoop's tool list.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SkillCreator:
    """Creates skills and hot-loads them into the running system."""

    def __init__(
        self,
        tool_registry: Any,
        tool_runtime: Any,
        agent_loop: Any,
        security_service: Any,
        project_root: Path,
    ) -> None:
        self._registry = tool_registry
        self._runtime = tool_runtime
        self._agent_loop = agent_loop
        self._security = security_service
        self._root = project_root
        self._contracts_dir = project_root / "system" / "tools" / "contracts" / "v1"
        self._impl_dir = project_root / "system" / "tools" / "implementations"
        self._created: list[dict[str, Any]] = []

    def create_and_load(
        self,
        tool_id: str,
        name: str,
        description: str,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        handler_code: str,
        handler_name: str = "",
        dependencies: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a tool contract + handler and hot-load into the system.

        Returns: {"status": "success", "tool_id": "...", "hot_loaded": True}
        """
        if not tool_id or not handler_code:
            return {"status": "error", "error": "tool_id and handler_code are required"}

        handler_name = handler_name or f"handle_{tool_id}"

        # 1. Install dependencies if needed
        if dependencies:
            self._install_deps(dependencies)

        # 2. Save contract JSON
        contract = {
            "id": tool_id,
            "name": name or tool_id,
            "category": "auto_generated",
            "description": description,
            "inputs": inputs or {},
            "outputs": outputs or {},
            "constraints": {"timeout_ms": 30000, "allowlist": []},
            "safety": {"level": "medium", "requires_confirmation": True},
            "auto_generated": True,
            "created_at": _now(),
        }
        contract_path = self._contracts_dir / f"{tool_id}.json"
        contract_path.write_text(json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8")

        # 3. Save Python handler
        impl_path = self._impl_dir / f"{tool_id}_auto.py"
        impl_path.write_text(handler_code, encoding="utf-8")

        # 4. Register contract in registry
        try:
            self._registry.register(contract)
        except Exception:
            pass  # May already exist if re-creating

        # 5. Dynamic import of handler
        try:
            spec = importlib.util.spec_from_file_location(
                f"capos_auto_{tool_id}", str(impl_path),
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"capos_auto_{tool_id}"] = module
            spec.loader.exec_module(module)
            handler = getattr(module, handler_name)
        except Exception as exc:
            return {"status": "error", "error": f"Failed to import handler: {exc}"}

        # 6. Register handler in runtime
        self._runtime.register_handler(tool_id, lambda params, contract, ctx=None: handler(params, contract))

        # 7. Update AgentLoop's tool list (no restart needed)
        from system.core.agent.tool_use_adapter import build_tool_definitions
        self._agent_loop._all_tools = build_tool_definitions(self._registry)
        # Reset default tools to include the new one
        self._agent_loop._default_tools = self._agent_loop._resolve_tools(None)

        # 8. Add to security rules (Level 2 by default)
        if self._security:
            self._security._confirm_tools.add(tool_id)

        # 9. Track creation
        record = {"tool_id": tool_id, "name": name, "created_at": _now(), "auto": True}
        self._created.append(record)

        # 10. Emit event
        try:
            from system.core.ui_bridge.event_bus import event_bus
            event_bus.emit("skill_created", {"tool_id": tool_id, "auto": True})
        except Exception:
            pass

        return {"status": "success", "tool_id": tool_id, "hot_loaded": True, "contract_path": str(contract_path)}

    @property
    def created_skills(self) -> list[dict[str, Any]]:
        return list(self._created)

    @staticmethod
    def _install_deps(deps: list[str]) -> None:
        import subprocess
        for dep in deps:
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", dep],
                    capture_output=True, timeout=60,
                )
            except Exception:
                pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
