from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from system.shared.base_registry import BaseRegistry
from system.shared.schema_validation import SchemaValidationError

_TOKEN_PATTERN = re.compile(r"\{\{([^{}]+)\}\}")
_ALLOWED_VARIABLE_PATTERNS = (
    re.compile(r"^inputs\.[A-Za-z0-9_.-]+$"),
    re.compile(r"^state\.[A-Za-z0-9_.-]+$"),
    re.compile(r"^steps\.[a-z]+(?:_[a-z0-9]+)*\.outputs\.[A-Za-z0-9_.-]+$"),
    re.compile(r"^runtime\.[A-Za-z0-9_.-]+$"),
)


class CapabilityRegistry(BaseRegistry):
    """Registry for capability contracts."""

    def __init__(self, schema_path: str | Path | None = None):
        default_schema = Path(__file__).resolve().parents[1] / "contracts" / "capability_contract.schema.json"
        super().__init__(schema_path or default_schema)

    def _post_schema_validation(self, contract: dict[str, Any], source: str) -> None:
        strategy = contract.get("strategy", {})
        all_steps = list(strategy.get("steps", []))
        all_steps.extend(strategy.get("fallback_steps", []))
        for step in all_steps:
            params = step.get("params", {})
            for value in _iter_strings(params):
                self._validate_template_variables(value, source)
            condition = step.get("condition")
            if isinstance(condition, str):
                self._validate_condition_variables(condition, source)

    @staticmethod
    def _validate_template_variables(value: str, source: str) -> None:
        for match in _TOKEN_PATTERN.findall(value):
            expr = match.strip()
            if not any(pattern.match(expr) for pattern in _ALLOWED_VARIABLE_PATTERNS):
                raise SchemaValidationError(
                    f"{source}: invalid strategy variable '{{{{{expr}}}}}'. "
                    "Allowed roots: inputs., state., steps.<step_id>.outputs., runtime."
                )

    @classmethod
    def _validate_condition_variables(cls, condition: str, source: str) -> None:
        for match in _TOKEN_PATTERN.findall(condition):
            expr = match.strip()
            if not any(pattern.match(expr) for pattern in _ALLOWED_VARIABLE_PATTERNS):
                raise SchemaValidationError(
                    f"{source}: invalid condition variable '{{{{{expr}}}}}'. "
                    "Allowed roots: inputs., state., steps.<step_id>.outputs., runtime."
                )


def _iter_strings(node: Any):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for item in node.values():
            yield from _iter_strings(item)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_strings(item)
