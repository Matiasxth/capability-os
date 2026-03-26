from __future__ import annotations

import re
from typing import Any, Callable

from system.capabilities.registry import CapabilityRegistry


class PlanValidator:
    """Validates normalized plans against registry contracts and integration state."""

    _STEP_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        integration_status_resolver: Callable[[str], str | None] | None = None,
    ):
        self.capability_registry = capability_registry
        self.integration_status_resolver = integration_status_resolver

    def validate(self, plan: dict[str, Any]) -> dict[str, Any]:
        errors: list[dict[str, Any]] = []
        if not isinstance(plan, dict):
            return {
                "valid": False,
                "errors": [{"code": "invalid_plan", "message": "Plan must be an object."}],
            }

        plan_type = plan.get("type")
        if plan_type not in {"capability", "sequence", "unknown"}:
            errors.append({"code": "invalid_plan_type", "message": "Plan type must be capability, sequence, or unknown."})
            return {"valid": False, "errors": errors}

        if plan_type == "unknown":
            return {
                "valid": False,
                "errors": [{"code": "unknown_intent", "message": "Intent could not be mapped to executable capabilities."}],
            }

        steps = plan.get("steps", [])
        if not isinstance(steps, list) or not steps:
            errors.append({"code": "missing_steps", "message": "Plan must include at least one step."})
            return {"valid": False, "errors": errors}

        step_ids_seen: set[str] = set()
        for index, step in enumerate(steps):
            step_ref = f"step_{index + 1}"
            if not isinstance(step, dict):
                errors.append({"code": "invalid_step", "message": "Each plan step must be an object.", "step_id": step_ref})
                continue

            step_id = step.get("step_id")
            if not isinstance(step_id, str) or not step_id.strip():
                errors.append(
                    {
                        "code": "missing_step_id",
                        "message": "Each step requires non-empty 'step_id'.",
                        "step_id": step_ref,
                    }
                )
                continue
            step_id = step_id.strip()
            if step_id in step_ids_seen:
                errors.append(
                    {
                        "code": "duplicate_step_id",
                        "message": f"Duplicate step_id '{step_id}'.",
                        "step_id": step_id,
                    }
                )
                continue
            step_ids_seen.add(step_id)

            if self._STEP_ID_PATTERN.match(step_id) is None:
                errors.append(
                    {
                        "code": "invalid_step_id",
                        "message": f"step_id '{step_id}' must match naming canon [a-z][a-z0-9_]*.",
                        "step_id": step_id,
                    }
                )

            capability_id = step.get("capability")
            if not isinstance(capability_id, str) or not capability_id.strip():
                errors.append(
                    {
                        "code": "missing_capability",
                        "message": "Step requires non-empty 'capability'.",
                        "step_id": step_id,
                    }
                )
                continue
            capability_id = capability_id.strip()

            contract = self.capability_registry.get(capability_id)
            if contract is None:
                errors.append(
                    {
                        "code": "capability_not_found",
                        "message": f"Capability '{capability_id}' is not registered.",
                        "step_id": step_id,
                        "capability": capability_id,
                    }
                )
                continue

            inputs = step.get("inputs", {})
            if inputs is None:
                inputs = {}
            if not isinstance(inputs, dict):
                errors.append(
                    {
                        "code": "invalid_inputs",
                        "message": "Step 'inputs' must be an object.",
                        "step_id": step_id,
                        "capability": capability_id,
                    }
                )
                continue

            self._validate_inputs(step_id, capability_id, contract, inputs, errors)
            self._validate_integrations(step_id, capability_id, contract, errors)

        return {"valid": len(errors) == 0, "errors": errors}

    def _validate_inputs(
        self,
        step_id: str,
        capability_id: str,
        contract: dict[str, Any],
        inputs: dict[str, Any],
        errors: list[dict[str, Any]],
    ) -> None:
        contract_inputs = contract.get("inputs", {})
        if not isinstance(contract_inputs, dict):
            return

        allowed_fields = set(contract_inputs.keys())
        unknown_fields = [field for field in inputs.keys() if field not in allowed_fields]
        if unknown_fields:
            errors.append(
                {
                    "code": "unknown_input_fields",
                    "message": f"Unknown input fields for '{capability_id}': {', '.join(sorted(unknown_fields))}.",
                    "step_id": step_id,
                    "capability": capability_id,
                    "fields": sorted(unknown_fields),
                }
            )

        missing_required: list[str] = []
        for field_name, field_contract in contract_inputs.items():
            required = isinstance(field_contract, dict) and field_contract.get("required") is True
            if not required:
                continue
            value = inputs.get(field_name)
            if value is None:
                missing_required.append(field_name)
        if missing_required:
            errors.append(
                {
                    "code": "missing_required_inputs",
                    "message": f"Missing required inputs for '{capability_id}': {', '.join(sorted(missing_required))}.",
                    "step_id": step_id,
                    "capability": capability_id,
                    "fields": sorted(missing_required),
                }
            )

    def _validate_integrations(
        self,
        step_id: str,
        capability_id: str,
        contract: dict[str, Any],
        errors: list[dict[str, Any]],
    ) -> None:
        if self.integration_status_resolver is None:
            return

        requirements = contract.get("requirements", {})
        if not isinstance(requirements, dict):
            return
        required_integrations = requirements.get("integrations", [])
        if not isinstance(required_integrations, list):
            return

        for integration_id in required_integrations:
            if not isinstance(integration_id, str) or not integration_id:
                continue
            status = self.integration_status_resolver(integration_id)
            if status != "enabled":
                errors.append(
                    {
                        "code": "integration_not_enabled",
                        "message": f"Required integration '{integration_id}' is not enabled (status='{status}').",
                        "step_id": step_id,
                        "capability": capability_id,
                        "integration_id": integration_id,
                        "status": status,
                    }
                )
