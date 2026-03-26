from __future__ import annotations

from copy import deepcopy
from typing import Any


class PlanBuildError(ValueError):
    """Raised when interpreted intent cannot be converted into a plan."""


class PlanBuilder:
    """Converts intent interpreter output into a normalized execution plan."""

    def build(self, interpretation: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(interpretation, dict):
            raise PlanBuildError("Interpretation payload must be an object.")

        suggestion = interpretation.get("suggestion", {})
        if not isinstance(suggestion, dict):
            raise PlanBuildError("Interpretation field 'suggestion' must be an object.")

        suggestion_type = suggestion.get("type")
        if suggestion_type not in {"capability", "sequence", "unknown"}:
            raise PlanBuildError("Suggestion field 'type' must be capability, sequence, or unknown.")

        suggest_only = interpretation.get("suggest_only", True)
        if not isinstance(suggest_only, bool):
            suggest_only = True

        if suggestion_type == "unknown":
            return {
                "type": "unknown",
                "suggest_only": suggest_only,
                "steps": [],
            }

        if suggestion_type == "capability":
            capability_id = suggestion.get("capability")
            if not isinstance(capability_id, str) or not capability_id.strip():
                raise PlanBuildError("Capability suggestion requires non-empty 'capability'.")
            inputs = suggestion.get("inputs", {})
            if inputs is None:
                inputs = {}
            if not isinstance(inputs, dict):
                raise PlanBuildError("Capability suggestion field 'inputs' must be an object.")
            return {
                "type": "capability",
                "suggest_only": suggest_only,
                "steps": [
                    {
                        "step_id": "step_1",
                        "capability": capability_id.strip(),
                        "inputs": deepcopy(inputs),
                    }
                ],
            }

        raw_steps = suggestion.get("steps", [])
        if not isinstance(raw_steps, list):
            raise PlanBuildError("Sequence suggestion field 'steps' must be a list.")

        normalized_steps: list[dict[str, Any]] = []
        for index, raw_step in enumerate(raw_steps):
            if not isinstance(raw_step, dict):
                raise PlanBuildError("Each sequence step must be an object.")

            raw_step_id = raw_step.get("step_id")
            if isinstance(raw_step_id, str) and raw_step_id.strip():
                step_id = raw_step_id.strip()
            else:
                step_id = f"step_{index + 1}"

            capability_id = raw_step.get("capability")
            if not isinstance(capability_id, str) or not capability_id.strip():
                raise PlanBuildError(f"Step '{step_id}' requires non-empty 'capability'.")

            inputs = raw_step.get("inputs", {})
            if inputs is None:
                inputs = {}
            if not isinstance(inputs, dict):
                raise PlanBuildError(f"Step '{step_id}' field 'inputs' must be an object.")

            normalized_steps.append(
                {
                    "step_id": step_id,
                    "capability": capability_id.strip(),
                    "inputs": deepcopy(inputs),
                }
            )

        return {
            "type": "sequence",
            "suggest_only": suggest_only,
            "steps": normalized_steps,
        }
