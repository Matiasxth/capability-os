"""Integration service — moved from api_server.py god-object.

These functions handle integration listing, inspection, validation,
enable/disable. Called by integration_handlers.py.
"""
from __future__ import annotations

from typing import Any


def list_integrations(service: Any) -> list[dict[str, Any]]:
    """List all integrations with formatted state."""
    return service._list_integrations()


def inspect_integration(service: Any, integration_id: str) -> dict[str, Any]:
    """Get detailed info about an integration."""
    return service._inspect_integration(integration_id)


def validate_integration(service: Any, integration_id: str) -> dict[str, Any]:
    """Validate an integration."""
    return service._validate_integration(integration_id)


def enable_integration(service: Any, integration_id: str) -> dict[str, Any]:
    """Enable an integration."""
    return service._enable_integration(integration_id)


def disable_integration(service: Any, integration_id: str) -> dict[str, Any]:
    """Disable an integration."""
    return service._disable_integration(integration_id)
