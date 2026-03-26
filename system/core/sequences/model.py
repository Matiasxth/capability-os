from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


class SequenceValidationError(ValueError):
    """Raised when a sequence definition is invalid."""


_SEQUENCE_ID_PATTERN = re.compile(r"^[a-z]+(?:_[a-z0-9]+)*$")
_CAPABILITY_ID_PATTERN = re.compile(r"^[a-z]+(?:_[a-z0-9]+)+$")
_TOKEN_PATTERN = re.compile(r"\{\{([^{}]+)\}\}")
_STEP_REF_PATTERN = re.compile(r"^steps\.([a-z]+(?:_[a-z0-9]+)*)\.outputs\.[A-Za-z0-9_.-]+$")
_ALLOWED_VARIABLE_PATTERNS = (
    re.compile(r"^inputs\.[A-Za-z0-9_.-]+$"),
    re.compile(r"^state\.[A-Za-z0-9_.-]+$"),
    _STEP_REF_PATTERN,
)


@dataclass(frozen=True)
class SequenceStep:
    step_id: str
    capability: str
    inputs: dict[str, Any]


@dataclass(frozen=True)
class SequenceDefinition:
    sequence_id: str
    name: str
    steps: list[SequenceStep]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.sequence_id,
            "name": self.name,
            "steps": [
                {
                    "step_id": step.step_id,
                    "capability": step.capability,
                    "inputs": step.inputs,
                }
                for step in self.steps
            ],
        }


def parse_sequence_definition(payload: dict[str, Any]) -> SequenceDefinition:
    if not isinstance(payload, dict):
        raise SequenceValidationError("Sequence definition must be an object.")

    sequence_id = payload.get("id")
    if not isinstance(sequence_id, str) or not _SEQUENCE_ID_PATTERN.match(sequence_id):
        raise SequenceValidationError(
            "Sequence field 'id' must be snake_case (e.g. 'daily_build_sequence')."
        )

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise SequenceValidationError("Sequence field 'name' must be a non-empty string.")

    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise SequenceValidationError("Sequence field 'steps' must be a non-empty list.")

    parsed_steps: list[SequenceStep] = []
    seen_step_ids: set[str] = set()
    for index, raw_step in enumerate(raw_steps):
        parsed_step = _parse_step(raw_step, index=index)
        if parsed_step.step_id in seen_step_ids:
            raise SequenceValidationError(f"Duplicate sequence step_id '{parsed_step.step_id}'.")
        seen_step_ids.add(parsed_step.step_id)
        parsed_steps.append(parsed_step)

    _validate_step_templates(parsed_steps)
    return SequenceDefinition(sequence_id=sequence_id, name=name.strip(), steps=parsed_steps)


def _parse_step(raw_step: Any, *, index: int) -> SequenceStep:
    if not isinstance(raw_step, dict):
        raise SequenceValidationError(f"Sequence step at index {index} must be an object.")

    step_id = raw_step.get("step_id")
    if not isinstance(step_id, str) or not _SEQUENCE_ID_PATTERN.match(step_id):
        raise SequenceValidationError(
            f"Sequence step at index {index} has invalid 'step_id'. Use snake_case."
        )

    capability = raw_step.get("capability")
    if not isinstance(capability, str) or not _CAPABILITY_ID_PATTERN.match(capability):
        raise SequenceValidationError(
            f"Sequence step '{step_id}' has invalid 'capability'. Use capability id snake_case."
        )

    inputs = raw_step.get("inputs")
    if not isinstance(inputs, dict):
        raise SequenceValidationError(f"Sequence step '{step_id}' field 'inputs' must be an object.")

    return SequenceStep(step_id=step_id, capability=capability, inputs=inputs)


def _validate_step_templates(steps: list[SequenceStep]) -> None:
    available_previous_steps: set[str] = set()
    for step in steps:
        for value in _iter_strings(step.inputs):
            for token in _TOKEN_PATTERN.findall(value):
                expr = token.strip()
                if not any(pattern.match(expr) for pattern in _ALLOWED_VARIABLE_PATTERNS):
                    raise SequenceValidationError(
                        f"Step '{step.step_id}' uses unsupported variable '{{{{{expr}}}}}'. "
                        "Allowed roots: inputs., state., steps.<step_id>.outputs."
                    )

                step_ref_match = _STEP_REF_PATTERN.match(expr)
                if step_ref_match:
                    referenced_step = step_ref_match.group(1)
                    if referenced_step not in available_previous_steps:
                        raise SequenceValidationError(
                            f"Step '{step.step_id}' references step '{referenced_step}' "
                            "before it is available."
                        )
        available_previous_steps.add(step.step_id)


def _iter_strings(node: Any):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for item in node.values():
            yield from _iter_strings(item)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_strings(item)
