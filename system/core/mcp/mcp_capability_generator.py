"""Generates capability contract proposals from MCP tools.

For each tool registered via the MCP Tool Bridge, this module builds a
capability contract that wraps the tool in a single-step sequential strategy.
Contracts are saved as **proposals** in ``proposals_dir`` — they are NOT
installed in the CapabilityRegistry until the user explicitly approves them.

Spec section 14 rule: the system proposes, the user confirms.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from system.core.mcp.mcp_tool_bridge import MCPToolBridge, mcp_tool_id


def build_capability_contract(tool_contract: dict[str, Any]) -> dict[str, Any]:
    """Build a capability contract that wraps a single MCP tool contract.

    The capability id mirrors the tool id (both use ``mcp_<server>_<tool>``).
    """
    tool_id = tool_contract.get("id", "mcp_unknown_unknown")
    description = tool_contract.get("description", tool_id)
    inputs = deepcopy(tool_contract.get("inputs", {}))
    timeout_ms = tool_contract.get("constraints", {}).get("timeout_ms", 30000)

    # Build strategy params: forward all inputs as {{inputs.<field>}}
    params: dict[str, Any] = {}
    for field_name in inputs:
        params[field_name] = f"{{{{inputs.{field_name}}}}}"

    return {
        "id": tool_id,
        "name": tool_contract.get("name", tool_id),
        "domain": "integraciones",
        "type": "integration",
        "description": description,
        "inputs": inputs,
        "outputs": deepcopy(tool_contract.get("outputs", {"content": {"type": "array"}})),
        "requirements": {
            "tools": [tool_id],
            "capabilities": [],
            "integrations": [],
        },
        "strategy": {
            "mode": "sequential",
            "steps": [
                {
                    "step_id": "call_mcp",
                    "action": tool_id,
                    "params": params,
                }
            ],
        },
        "exposure": {
            "visible_to_user": True,
            "trigger_phrases": [tool_id.replace("_", " ")],
        },
        "lifecycle": {
            "version": "1.0.0",
            "status": "experimental",
        },
    }


class MCPCapabilityGenerator:
    """Generates capability proposals from bridged MCP tools."""

    def __init__(self, tool_bridge: MCPToolBridge, proposals_dir: str | Path):
        self._bridge = tool_bridge
        self._proposals_dir = Path(proposals_dir).resolve()

    def generate_proposals(self) -> list[dict[str, Any]]:
        """Generate a capability proposal for every bridged MCP tool.

        Returns a list of ``{capability_id, proposal_path, contract}`` dicts.
        Existing proposals with the same id are overwritten.
        """
        bridged = self._bridge.list_bridged_tools()
        results: list[dict[str, Any]] = []

        for entry in bridged:
            tool_id = entry["tool_id"]
            tool_contract = self._bridge._tool_registry.get(tool_id)
            if tool_contract is None:
                continue

            contract = build_capability_contract(tool_contract)
            path = self._save_proposal(contract)
            results.append({
                "capability_id": contract["id"],
                "proposal_path": str(path),
                "contract": deepcopy(contract),
            })

        return results

    def generate_for_tool(self, tool_id: str) -> dict[str, Any] | None:
        """Generate a single capability proposal for a specific tool_id."""
        tool_contract = self._bridge._tool_registry.get(tool_id)
        if tool_contract is None:
            return None

        contract = build_capability_contract(tool_contract)
        path = self._save_proposal(contract)
        return {
            "capability_id": contract["id"],
            "proposal_path": str(path),
            "contract": deepcopy(contract),
        }

    def get_proposal(self, capability_id: str) -> dict[str, Any] | None:
        path = self._proposals_dir / f"{capability_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def list_proposals(self) -> list[str]:
        if not self._proposals_dir.exists():
            return []
        return sorted(p.stem for p in self._proposals_dir.glob("*.json"))

    def delete_proposal(self, capability_id: str) -> bool:
        path = self._proposals_dir / f"{capability_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def _save_proposal(self, contract: dict[str, Any]) -> Path:
        self._proposals_dir.mkdir(parents=True, exist_ok=True)
        cap_id = contract.get("id", "unknown")
        path = self._proposals_dir / f"{cap_id}.json"
        path.write_text(
            json.dumps(contract, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path
