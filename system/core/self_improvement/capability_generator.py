"""Generates capability contract proposals from gap descriptions.

Uses the LLM (via LLMClient) to produce a complete capability contract JSON,
validates it against the capability_contract.schema.json, and saves it as a
proposal file.  The contract is **never** installed in the registry — only
persisted as a proposal for the user to review and approve.

Spec section 14 rule: the system proposes, the user confirms.
"""
from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from system.capabilities.registry import CapabilityRegistry
from system.core.interpretation.llm_client import LLMClient, LLMClientError
from system.shared.schema_validation import SchemaValidationError


class CapabilityGeneratorError(RuntimeError):
    """Raised when capability generation fails."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


# ---------------------------------------------------------------------------
# Prompt template for contract generation
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """
You are a capability contract generator for Capability OS.
Rules:
1. Return ONLY valid JSON — no prose, no markdown, no code fences.
2. The JSON must follow the capability contract schema exactly.
3. Required top-level fields: id, name, domain, type, description,
   inputs, outputs, requirements, strategy, exposure, lifecycle.
4. id must be snake_case: verb_object (e.g. send_email).
5. domain must be one of: desarrollo, archivos, ejecucion, web,
   integraciones, automatizacion, observacion.
6. type must be one of: base, composed, integration, generated.
7. strategy.mode must be one of: sequential, conditional, retry_policy, fallback.
8. Each strategy step needs: step_id, action, params.
9. action must follow category_verb_object pattern
   (e.g. network_http_post, filesystem_read_file).
10. Variables must use explicit origins only:
    {{inputs.<field>}}, {{state.<field>}},
    {{steps.<step_id>.outputs.<field>}}, {{runtime.<field>}}.
11. lifecycle.status must be "experimental".
12. lifecycle.version must be "1.0.0".
""".strip()

_USER_PROMPT_TEMPLATE = """
Generate a capability contract for the following:

Capability ID: {capability_id}
Domain: {domain}
Description: {description}

Available tools (use these in strategy steps):
{tool_ids}

Return the complete JSON contract only.
""".strip()


class CapabilityGenerator:
    """Generates capability contract proposals via LLM and validates them."""

    def __init__(
        self,
        llm_client: LLMClient,
        capability_registry: CapabilityRegistry,
        proposals_dir: str | Path,
    ):
        self._llm_client = llm_client
        self._registry = capability_registry
        self._proposals_dir = Path(proposals_dir).resolve()
        self._schema_path = (
            Path(__file__).resolve().parents[2]
            / "capabilities"
            / "contracts"
            / "capability_contract.schema.json"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_proposal(self, gap: dict[str, Any]) -> dict[str, Any]:
        """Generate a capability contract proposal from a gap record.

        Returns:
            dict with keys: capability_id, proposal_path, contract, validated.
        """
        capability_id = gap.get("capability_id") or gap.get("suggested_capability") or "unknown_capability"
        domain = gap.get("domain", "ejecucion")
        description = gap.get("description") or gap.get("sample_intent") or gap.get("intent") or capability_id

        contract = self._generate_contract(capability_id, domain, description)
        validated = self._validate_contract(contract)

        proposal_path = self._save_proposal(capability_id, contract)

        return {
            "capability_id": capability_id,
            "proposal_path": str(proposal_path),
            "contract": deepcopy(contract),
            "validated": validated,
        }

    def get_proposal(self, capability_id: str) -> dict[str, Any] | None:
        """Load a previously saved proposal from disk."""
        path = self._proposals_dir / f"{capability_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def list_proposals(self) -> list[str]:
        """Return capability_ids of all saved proposals."""
        if not self._proposals_dir.exists():
            return []
        return sorted(
            p.stem for p in self._proposals_dir.glob("*.json")
        )

    def delete_proposal(self, capability_id: str) -> bool:
        """Remove a proposal file. Returns True if deleted."""
        path = self._proposals_dir / f"{capability_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _generate_contract(
        self, capability_id: str, domain: str, description: str,
    ) -> dict[str, Any]:
        """Call LLM to generate a contract, falling back to a template on failure."""
        tool_ids = ", ".join(sorted(set(
            t.get("id", "") for t in (self._registry.list_all() or [])
            if isinstance(t, dict) and t.get("id")
        )))[:2000]

        prompt = _USER_PROMPT_TEMPLATE.format(
            capability_id=capability_id,
            domain=domain,
            description=description,
            tool_ids=tool_ids or "(no tools registered)",
        )

        try:
            raw = self._llm_client.complete(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=prompt,
            )
            contract = _parse_json_response(raw)
            if contract is not None:
                return contract
        except LLMClientError:
            pass

        # Fallback: build a minimal valid contract without LLM
        return _fallback_contract(capability_id, domain, description)

    def _validate_contract(self, contract: dict[str, Any]) -> bool:
        """Validate against schema via CapabilityRegistry (dry-run). Returns True if valid."""
        try:
            temp_registry = CapabilityRegistry(schema_path=self._schema_path)
            temp_registry.register(deepcopy(contract), source="capability_generator")
            return True
        except (SchemaValidationError, Exception):
            return False

    def _save_proposal(self, capability_id: str, contract: dict[str, Any]) -> Path:
        self._proposals_dir.mkdir(parents=True, exist_ok=True)
        path = self._proposals_dir / f"{capability_id}.json"
        path.write_text(
            json.dumps(contract, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_json_response(raw: str) -> dict[str, Any] | None:
    """Extract a JSON object from LLM output (handles markdown fences)."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return None


def _fallback_contract(
    capability_id: str, domain: str, description: str,
) -> dict[str, Any]:
    """Build a minimal valid contract when LLM is unavailable."""
    valid_domains = {
        "desarrollo", "archivos", "ejecucion", "web",
        "integraciones", "automatizacion", "observacion",
    }
    if domain not in valid_domains:
        domain = "ejecucion"

    return {
        "id": capability_id,
        "name": capability_id.replace("_", " ").title(),
        "domain": domain,
        "type": "generated",
        "description": description,
        "inputs": {
            "input_value": {"type": "string", "required": True, "description": "Primary input."},
        },
        "outputs": {
            "status": {"type": "string"},
        },
        "requirements": {
            "tools": ["execution_run_command"],
            "capabilities": [],
            "integrations": [],
        },
        "strategy": {
            "mode": "sequential",
            "steps": [
                {
                    "step_id": "run_action",
                    "action": "execution_run_command",
                    "params": {"command": "echo {{inputs.input_value}}"},
                }
            ],
        },
        "exposure": {
            "visible_to_user": True,
            "trigger_phrases": [capability_id.replace("_", " ")],
        },
        "lifecycle": {
            "version": "1.0.0",
            "status": "experimental",
        },
    }
