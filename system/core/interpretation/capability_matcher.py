from __future__ import annotations

from typing import Any

from system.capabilities.registry import CapabilityRegistry


class CapabilityMatchError(ValueError):
    """Raised when interpreted capabilities do not match registered contracts."""


class CapabilityMatcher:
    """Validates interpreted payload against capability registry."""

    def __init__(self, capability_registry: CapabilityRegistry):
        self.capability_registry = capability_registry

    def validate(self, interpreted: dict[str, Any]) -> dict[str, Any]:
        intent_type = interpreted.get("type")
        if intent_type == "unknown":
            return interpreted

        if intent_type == "capability":
            capability_id = interpreted.get("capability")
            contract = self.capability_registry.get(capability_id)
            if contract is None:
                raise CapabilityMatchError(f"Capability '{capability_id}' is not registered.")

            provided_inputs = interpreted.get("inputs", {})
            if not isinstance(provided_inputs, dict):
                raise CapabilityMatchError("Capability interpreted inputs must be an object.")

            allowed_fields = set(contract.get("inputs", {}).keys())
            unknown_fields = [field for field in provided_inputs.keys() if field not in allowed_fields]
            if unknown_fields:
                unknown_str = ", ".join(sorted(unknown_fields))
                raise CapabilityMatchError(
                    f"Capability '{capability_id}' received unknown input fields: {unknown_str}."
                )
            return interpreted

        if intent_type == "sequence":
            steps = interpreted.get("steps", [])
            if not isinstance(steps, list):
                raise CapabilityMatchError("Sequence interpretation 'steps' must be a list.")
            for step in steps:
                if not isinstance(step, dict):
                    raise CapabilityMatchError("Sequence step must be an object.")

                step_id = step.get("step_id")
                if not isinstance(step_id, str) or not step_id:
                    raise CapabilityMatchError("Sequence step requires non-empty 'step_id'.")

                capability_id = step.get("capability")
                contract = self.capability_registry.get(capability_id)
                if contract is None:
                    raise CapabilityMatchError(f"Sequence step references unknown capability '{capability_id}'.")

                provided_inputs = step.get("inputs", {})
                if not isinstance(provided_inputs, dict):
                    raise CapabilityMatchError(
                        f"Sequence step '{step_id}' inputs must be an object."
                    )

                allowed_fields = set(contract.get("inputs", {}).keys())
                unknown_fields = [field for field in provided_inputs.keys() if field not in allowed_fields]
                if unknown_fields:
                    unknown_str = ", ".join(sorted(unknown_fields))
                    raise CapabilityMatchError(
                        f"Sequence step '{step_id}' capability '{capability_id}' "
                        f"received unknown input fields: {unknown_str}."
                    )

                required_fields: list[str] = []
                for field_name, field_contract in contract.get("inputs", {}).items():
                    if isinstance(field_contract, dict) and field_contract.get("required") is True:
                        required_fields.append(field_name)
                missing = [
                    field_name
                    for field_name in required_fields
                    if field_name not in provided_inputs or provided_inputs[field_name] is None
                ]
                if missing:
                    missing_str = ", ".join(sorted(missing))
                    raise CapabilityMatchError(
                        f"Sequence step '{step_id}' capability '{capability_id}' "
                        f"is missing required input fields: {missing_str}."
                    )
            return interpreted

        raise CapabilityMatchError("Unsupported interpreted type.")
