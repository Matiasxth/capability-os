from __future__ import annotations

import inspect
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from system.tools.registry import ToolRegistry


class ToolExecutionError(RuntimeError):
    """Raised when tool execution cannot be completed in runtime."""


class ToolRuntime:
    """Runtime dispatcher for registered tool handlers (stub or real)."""

    def __init__(self, tool_registry: ToolRegistry, workspace_root: str | Path | None = None):
        self.tool_registry = tool_registry
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self._handlers: dict[str, Callable[..., Any]] = {}
        self._aliases: dict[str, str] = {}

    def register_handler(self, tool_id: str, handler: Callable[..., Any]) -> None:
        if not callable(handler):
            raise ToolExecutionError("Tool handler must be callable.")
        self._handlers[tool_id] = handler

    def register_stub(self, tool_id: str, handler: Callable[[dict[str, Any]], Any]) -> None:
        self.register_handler(tool_id, handler)

    def register_alias(self, alias_tool_id: str, canonical_tool_id: str) -> None:
        if not isinstance(alias_tool_id, str) or not alias_tool_id:
            raise ToolExecutionError("Alias tool id must be a non-empty string.")
        if not isinstance(canonical_tool_id, str) or not canonical_tool_id:
            raise ToolExecutionError("Canonical tool id must be a non-empty string.")
        if alias_tool_id == canonical_tool_id:
            return
        self._aliases[alias_tool_id] = canonical_tool_id

    def resolve_action(self, action: str) -> str:
        resolved = action
        visited: set[str] = set()
        while resolved in self._aliases:
            if resolved in visited:
                raise ToolExecutionError(f"Alias cycle detected while resolving tool '{action}'.")
            visited.add(resolved)
            resolved = self._aliases[resolved]
        return resolved

    def has_tool(self, tool_id: str) -> bool:
        resolved = self.resolve_action(tool_id)
        return self.tool_registry.get(resolved) is not None

    def execute(self, action: str, params: dict[str, Any]) -> Any:
        resolved_action = self.resolve_action(action)
        tool_contract = self.tool_registry.get(resolved_action)
        if tool_contract is None:
            raise ToolExecutionError(f"Tool '{action}' is not registered.")

        handler = self._handlers.get(resolved_action)
        if handler is None:
            raise ToolExecutionError(f"Tool '{action}' has no registered handler in this phase.")

        try:
            payload = deepcopy(params)
            arity = _callable_arity(handler)
            if arity <= 1:
                result = handler(payload)
            elif arity == 2:
                result = handler(payload, deepcopy(tool_contract))
            else:
                context = {"workspace_root": str(self.workspace_root)}
                result = handler(payload, deepcopy(tool_contract), context)
        except Exception as exc:  # pragma: no cover - wrapped for engine assertions
            raise ToolExecutionError(f"Tool '{action}' failed: {exc}") from exc

        return deepcopy(result)


def _callable_arity(handler: Callable[..., Any]) -> int:
    signature = inspect.signature(handler)
    count = 0
    for param in signature.parameters.values():
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
            count += 1
    return count
