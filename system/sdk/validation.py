"""Contract validation — verify that plugins and services implement their Protocols.

SDK v2: Now checks method signatures (parameter count) in addition to
attribute existence. Used both in tests and optionally in production
via ``ServiceContainer(strict_contracts=True)``.
"""
from __future__ import annotations

import inspect
from typing import Any


def validate_contract(contract_type: type, implementation: Any) -> list[str]:
    """Check if implementation satisfies a Protocol contract.

    Validates:
    - All public methods/properties exist on the implementation
    - Methods are callable
    - Parameter count matches (excluding self)

    Returns a list of violation messages (empty = valid).
    """
    violations: list[str] = []

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

        # Check callability
        if callable(proto_attr) and not callable(impl_attr):
            violations.append(f"{name}: expected callable, got {type(impl_attr).__name__}")
            continue

        # Check parameter count for methods
        if callable(proto_attr) and callable(impl_attr):
            try:
                proto_sig = inspect.signature(proto_attr)
                impl_sig = inspect.signature(impl_attr)
                proto_params = [p for p in proto_sig.parameters if p != "self"]
                impl_params = [p for p in impl_sig.parameters if p != "self"]
                # Allow **kwargs on impl side (more permissive is OK)
                impl_has_var_kw = any(
                    impl_sig.parameters[p].kind == inspect.Parameter.VAR_KEYWORD
                    for p in impl_params
                )
                proto_required = sum(
                    1 for p in proto_params
                    if proto_sig.parameters[p].default is inspect.Parameter.empty
                    and proto_sig.parameters[p].kind not in (
                        inspect.Parameter.VAR_POSITIONAL,
                        inspect.Parameter.VAR_KEYWORD,
                    )
                )
                impl_required = sum(
                    1 for p in impl_params
                    if impl_sig.parameters[p].default is inspect.Parameter.empty
                    and impl_sig.parameters[p].kind not in (
                        inspect.Parameter.VAR_POSITIONAL,
                        inspect.Parameter.VAR_KEYWORD,
                    )
                )
                if not impl_has_var_kw and impl_required > len(proto_params):
                    violations.append(
                        f"{name}: impl requires {impl_required} params but "
                        f"contract declares {len(proto_params)}"
                    )
            except (ValueError, TypeError):
                pass  # Can't inspect — skip signature check

    return violations


def validate_plugin(plugin: Any) -> list[str]:
    """Validate that a plugin implements the BasePlugin interface.

    Checks:
    - Required attributes: plugin_id, plugin_name, version, dependencies
    - Required methods: initialize(ctx), start(), stop()
    """
    violations: list[str] = []

    for attr in ("plugin_id", "plugin_name", "version", "dependencies"):
        if not hasattr(plugin, attr):
            violations.append(f"Missing attribute: {attr}")

    for method in ("initialize", "start", "stop"):
        fn = getattr(plugin, method, None)
        if fn is None or not callable(fn):
            violations.append(f"Missing method: {method}()")

    return violations
