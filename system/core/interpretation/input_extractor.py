from __future__ import annotations

from copy import deepcopy
from typing import Any


class InputExtractionError(ValueError):
    """Raised when interpreted payload cannot be normalized."""


class InputExtractor:
    """Normalizes interpreted payload values and enforces basic structure."""

    def extract(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise InputExtractionError("Interpreted payload must be an object.")

        parsed = deepcopy(payload)
        intent_type = parsed.get("type")
        if intent_type not in {"capability", "sequence", "unknown"}:
            raise InputExtractionError("Field 'type' must be capability, sequence, or unknown.")

        if intent_type == "unknown":
            return {"type": "unknown"}

        if intent_type == "capability":
            capability = parsed.get("capability")
            if not isinstance(capability, str) or not capability.strip():
                raise InputExtractionError("Capability interpretation requires non-empty 'capability'.")
            inputs = parsed.get("inputs", {})
            if inputs is None:
                inputs = {}
            if not isinstance(inputs, dict):
                raise InputExtractionError("Capability interpretation field 'inputs' must be an object.")
            return {
                "type": "capability",
                "capability": capability.strip(),
                "inputs": self._clean_node(inputs),
            }

        steps = parsed.get("steps")
        if not isinstance(steps, list) or not steps:
            raise InputExtractionError("Sequence interpretation requires non-empty 'steps' list.")
        cleaned_steps: list[dict[str, Any]] = []
        for step in steps:
            if not isinstance(step, dict):
                raise InputExtractionError("Sequence step must be an object.")
            step_id = step.get("step_id")
            capability = step.get("capability")
            inputs = step.get("inputs", {})
            if not isinstance(step_id, str) or not step_id.strip():
                raise InputExtractionError("Sequence step requires non-empty 'step_id'.")
            if not isinstance(capability, str) or not capability.strip():
                raise InputExtractionError("Sequence step requires non-empty 'capability'.")
            if inputs is None:
                inputs = {}
            if not isinstance(inputs, dict):
                raise InputExtractionError("Sequence step 'inputs' must be an object.")
            cleaned_steps.append(
                {
                    "step_id": step_id.strip(),
                    "capability": capability.strip(),
                    "inputs": self._clean_node(inputs),
                }
            )
        return {"type": "sequence", "steps": cleaned_steps}

    def _clean_node(self, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            return {str(key).strip(): self._clean_node(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._clean_node(item) for item in value]
        return value
