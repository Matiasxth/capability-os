"""Contract validation — verify that plugins implement their declared Protocols."""
from __future__ import annotations

import inspect
from typing import Any, get_type_hints


def validate_contract(contract_type: type, implementation: Any) -> list[str]:
    """Check if implementation satisfies a Protocol contract.

    Returns a list of violation messages (empty = valid).
    """
    violations: list[str] = []
    impl_type = type(implementation)

    # Get all methods/properties defined in the Protocol
    for name in dir(contract_type):
        if name.startswith("_"):
            continue

        proto_attr = getattr(contract_type, name, None)
        if proto_attr is None:
            continue

        impl_attr = getattr(implementation, name, None)

        if impl_attr is None:
            violations.append(f"Missing: {name}")
            continue

        # Check if it's callable
        if callable(proto_attr) and not callable(impl_attr):
            violations.append(f"{name}: expected callable, got {type(impl_attr).__name__}")
            continue

    return violations


def validate_plugin(plugin: Any) -> list[str]:
    """Validate that a plugin implements the BasePlugin interface."""
    violations: list[str] = []

    for attr in ("plugin_id", "plugin_name", "version", "dependencies"):
        if not hasattr(plugin, attr):
            violations.append(f"Missing attribute: {attr}")

    for method in ("initialize", "start", "stop"):
        fn = getattr(plugin, method, None)
        if fn is None or not callable(fn):
            violations.append(f"Missing method: {method}()")

    return violations
