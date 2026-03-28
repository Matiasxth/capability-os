"""A2A Agent Card for Capability OS.

Generates the ``/.well-known/agent.json`` descriptor that allows other
A2A-compatible agents to discover this agent's skills.

Each capability with ``lifecycle.status == "ready"`` is exposed as a skill.
The card is rebuilt dynamically on every request so it always reflects the
live CapabilityRegistry.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from system.capabilities.registry import CapabilityRegistry


class AgentCardBuilder:
    """Builds an A2A Agent Card from the CapabilityRegistry."""

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        server_url: str = "http://localhost:8000",
    ):
        self._registry = capability_registry
        self._server_url = server_url.rstrip("/")

    def build(self) -> dict[str, Any]:
        """Return the full Agent Card dict."""
        return {
            "name": "Capability OS",
            "description": (
                "A modular agent that converts intents into executable, "
                "observable, and self-improving actions."
            ),
            "url": self._server_url,
            "version": "1.0.0",
            "protocolVersion": "0.2.0",
            "capabilities": {
                "streaming": True,
                "pushNotifications": False,
            },
            "authentication": {
                "schemes": [],
            },
            "defaultInputModes": ["text"],
            "defaultOutputModes": ["text"],
            "skills": self._build_skills(),
        }

    def _build_skills(self) -> list[dict[str, Any]]:
        skills: list[dict[str, Any]] = []
        for contract in self._registry.list_all():
            status = contract.get("lifecycle", {}).get("status")
            if status != "ready":
                continue
            skills.append(_contract_to_skill(contract))
        return skills


def _contract_to_skill(contract: dict[str, Any]) -> dict[str, Any]:
    """Convert a capability contract to an A2A skill descriptor."""
    inputs = contract.get("inputs", {})
    input_fields: list[str] = []
    for field_name, field_def in inputs.items():
        if isinstance(field_def, dict):
            desc = field_def.get("description", field_name)
            req = " (required)" if field_def.get("required") else ""
            input_fields.append(f"{field_name}: {field_def.get('type', 'string')}{req}")

    return {
        "id": contract["id"],
        "name": contract.get("name", contract["id"]),
        "description": contract.get("description", ""),
        "inputModes": ["text"],
        "outputModes": ["text"],
        "tags": [contract.get("domain", "general")],
    }
