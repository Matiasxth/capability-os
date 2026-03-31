"""SDK exception hierarchy.

All SDK-related errors inherit from ``SDKError``. This provides structured
error handling instead of generic KeyError/RuntimeError/string conversions.

Usage::

    from system.sdk.errors import ServiceNotFoundError, ContractViolationError

    try:
        svc = ctx.get_service(SomeContract)
    except ServiceNotFoundError:
        # handle missing service
"""
from __future__ import annotations


class SDKError(Exception):
    """Base exception for all SDK errors."""


# ---------------------------------------------------------------------------
# Service resolution
# ---------------------------------------------------------------------------

class ServiceNotFoundError(SDKError):
    """Requested service contract has no registered implementation."""

    def __init__(self, contract_name: str):
        self.contract_name = contract_name
        super().__init__(f"No service registered for {contract_name}")


# ---------------------------------------------------------------------------
# Contract validation
# ---------------------------------------------------------------------------

class ContractViolationError(SDKError):
    """A service implementation doesn't fully satisfy its Protocol contract."""

    def __init__(self, contract: str, implementation: str, violations: list[str]):
        self.contract = contract
        self.implementation = implementation
        self.violations = violations
        detail = ", ".join(violations[:5])
        if len(violations) > 5:
            detail += f" (+{len(violations) - 5} more)"
        super().__init__(f"{implementation} violates {contract}: {detail}")


# ---------------------------------------------------------------------------
# Plugin lifecycle
# ---------------------------------------------------------------------------

class PluginInitError(SDKError):
    """Plugin failed during initialization."""

    def __init__(self, plugin_id: str, cause: Exception):
        self.plugin_id = plugin_id
        self.cause = cause
        super().__init__(f"Plugin '{plugin_id}' initialization failed: {cause}")


class PluginStartError(SDKError):
    """Plugin failed during start."""

    def __init__(self, plugin_id: str, cause: Exception):
        self.plugin_id = plugin_id
        self.cause = cause
        super().__init__(f"Plugin '{plugin_id}' start failed: {cause}")


class PluginDependencyError(SDKError):
    """Required plugin dependency is missing or in error state."""

    def __init__(self, plugin_id: str, missing: str):
        self.plugin_id = plugin_id
        self.missing = missing
        super().__init__(f"Plugin '{plugin_id}' requires '{missing}' which is not available")


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

class PermissionDeniedError(SDKError):
    """Plugin attempted an action it doesn't have permission for."""

    def __init__(self, plugin_id: str, permission: str, reason: str = ""):
        self.plugin_id = plugin_id
        self.permission = permission
        self.reason = reason
        super().__init__(f"Plugin '{plugin_id}' denied '{permission}'" + (f": {reason}" if reason else ""))


class ToolExecutionSDKError(SDKError):
    """Tool execution failed with structured context."""

    def __init__(self, tool_id: str, message: str, params: dict | None = None):
        self.tool_id = tool_id
        self.params = params or {}
        super().__init__(f"Tool '{tool_id}': {message}")
