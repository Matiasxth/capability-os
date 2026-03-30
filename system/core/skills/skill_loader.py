"""Dynamic tool handler loading from skill packages."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Callable


def load_tool_handler(
    impl_path: Path,
    tool_id: str,
) -> Callable[..., dict[str, Any]] | None:
    """Load a tool handler function from a Python file.

    Looks for a function named ``handle`` or matching the tool_id
    in the module at impl_path. Returns None if not found.
    """
    try:
        spec = importlib.util.spec_from_file_location(
            f"skill_tool_{tool_id}", str(impl_path),
        )
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Try: handle() function first, then function named like the tool_id
        handler = getattr(module, "handle", None)
        if handler is None:
            handler = getattr(module, tool_id, None)
        if handler is None:
            handler = getattr(module, tool_id.replace("-", "_"), None)

        return handler if callable(handler) else None
    except Exception:
        return None
