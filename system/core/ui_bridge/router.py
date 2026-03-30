"""Lightweight HTTP router for Capability OS.

Maps (method, path) → handler function. Supports exact paths and
paths with ``{param}`` placeholders.

Usage::

    router = Router()
    router.add("GET", "/capabilities", list_capabilities)
    router.add("GET", "/capabilities/{capability_id}", get_capability)
    router.add("POST", "/execute", execute_capability)

    match = router.dispatch("GET", "/capabilities/read_file")
    # match = RouteMatch(handler=get_capability, params={"capability_id": "read_file"})
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable


# Handler signature: (service, payload, **path_params) -> APIResponse
HandlerFn = Callable[..., Any]


@dataclass
class RouteMatch:
    handler: HandlerFn
    params: dict[str, str] = field(default_factory=dict)


class Router:
    """Simple path-based HTTP router."""

    def __init__(self) -> None:
        self._exact: dict[tuple[str, str], HandlerFn] = {}
        self._patterns: list[tuple[str, re.Pattern[str], list[str], HandlerFn]] = []

    def add(self, method: str, path: str, handler: HandlerFn) -> None:
        """Register a route. Path can contain {param} placeholders."""
        method = method.upper()
        if "{" not in path:
            self._exact[(method, path)] = handler
        else:
            param_names: list[str] = []
            regex_parts: list[str] = []
            for segment in path.strip("/").split("/"):
                if segment.startswith("{") and segment.endswith("}"):
                    name = segment[1:-1]
                    param_names.append(name)
                    regex_parts.append(r"([^/]+)")
                else:
                    regex_parts.append(re.escape(segment))
            pattern = re.compile("^/" + "/".join(regex_parts) + "$")
            self._patterns.append((method, pattern, param_names, handler))

    def dispatch(self, method: str, path: str) -> RouteMatch | None:
        """Find the handler for a request. Returns None if no match."""
        method = method.upper()
        clean = path.rstrip("/") or "/"

        # Exact match first (fastest)
        handler = self._exact.get((method, clean))
        if handler is not None:
            return RouteMatch(handler=handler)

        # Pattern match
        for route_method, pattern, param_names, handler in self._patterns:
            if route_method != method:
                continue
            m = pattern.match(clean)
            if m:
                params = dict(zip(param_names, m.groups()))
                return RouteMatch(handler=handler, params=params)

        return None

    @property
    def route_count(self) -> int:
        return len(self._exact) + len(self._patterns)
