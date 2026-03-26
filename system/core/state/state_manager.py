from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Callable


class VariableResolutionError(ValueError):
    """Raised when a template variable is implicit or cannot be resolved."""


_TOKEN_PATTERN = re.compile(r"\{\{([^{}]+)\}\}")
_STEP_PATTERN = re.compile(r"^steps\.([a-z]+(?:_[a-z0-9]+)*)\.outputs(?:\.(.+))?$")


class StateManager:
    """Stores runtime input/state and resolves explicit template variables."""

    def __init__(self, inputs: dict[str, Any] | None = None):
        self.inputs: dict[str, Any] = deepcopy(inputs or {})
        self.state: dict[str, Any] = {}
        self.step_outputs: dict[str, Any] = {}
        self._runtime_provider: Callable[[], dict[str, Any]] = lambda: {}

    def set_runtime_provider(self, provider: Callable[[], dict[str, Any]]) -> None:
        self._runtime_provider = provider

    def update_state(self, patch: dict[str, Any] | None) -> None:
        if not patch:
            return
        if not isinstance(patch, dict):
            raise VariableResolutionError("State patch must be an object.")
        self.state.update(deepcopy(patch))

    def record_step_output(self, step_id: str, output: Any) -> None:
        self.step_outputs[step_id] = deepcopy(output)

    def resolve_templates(self, value: Any) -> Any:
        if isinstance(value, str):
            return self._resolve_string(value)
        if isinstance(value, list):
            return [self.resolve_templates(item) for item in value]
        if isinstance(value, dict):
            return {key: self.resolve_templates(item) for key, item in value.items()}
        return value

    def _resolve_string(self, template: str) -> Any:
        matches = list(_TOKEN_PATTERN.finditer(template))
        if not matches:
            return template

        if len(matches) == 1 and matches[0].span() == (0, len(template)):
            expr = matches[0].group(1).strip()
            return self.resolve_expression(expr)

        rendered = template
        for match in matches:
            expr = match.group(1).strip()
            resolved = self.resolve_expression(expr)
            if isinstance(resolved, (dict, list)):
                raise VariableResolutionError(
                    f"Cannot interpolate non-scalar variable '{{{{{expr}}}}}' inside string template."
                )
            rendered = rendered.replace(match.group(0), "" if resolved is None else str(resolved))
        return rendered

    def resolve_expression(self, expression: str) -> Any:
        if expression.startswith("inputs."):
            return self._resolve_path(self.inputs, expression[len("inputs.") :], expression)

        if expression.startswith("state."):
            return self._resolve_path(self.state, expression[len("state.") :], expression)

        if expression.startswith("runtime."):
            runtime = self._runtime_provider() or {}
            return self._resolve_path(runtime, expression[len("runtime.") :], expression)

        step_match = _STEP_PATTERN.match(expression)
        if step_match:
            step_id, remainder = step_match.groups()
            if step_id not in self.step_outputs:
                raise VariableResolutionError(
                    f"Unknown step output reference '{{{{{expression}}}}}': step_id '{step_id}' was not executed."
                )
            step_value = self.step_outputs[step_id]
            if not remainder:
                return deepcopy(step_value)
            return self._resolve_path(step_value, remainder, expression)

        raise VariableResolutionError(
            f"Implicit or unsupported variable '{{{{{expression}}}}}'. "
            "Allowed roots: inputs., state., steps.<step_id>.outputs., runtime."
        )

    @staticmethod
    def _resolve_path(root: Any, dotted_path: str, expression: str) -> Any:
        if not dotted_path:
            raise VariableResolutionError(f"Incomplete variable reference '{{{{{expression}}}}}'.")

        current = root
        for token in dotted_path.split("."):
            if isinstance(current, dict) and token in current:
                current = current[token]
            elif isinstance(current, list) and token.isdigit():
                index = int(token)
                if index < 0 or index >= len(current):
                    raise VariableResolutionError(
                        f"Variable '{{{{{expression}}}}}' index '{token}' is out of bounds."
                    )
                current = current[index]
            else:
                raise VariableResolutionError(f"Variable '{{{{{expression}}}}}' does not exist.")
        return deepcopy(current)
