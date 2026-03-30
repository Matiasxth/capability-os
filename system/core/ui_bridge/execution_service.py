"""Execution orchestration — moved from api_server.py god-object.

These functions handle capability execution, sequence execution, and
execution storage. They are called by capability_handlers.py.
"""
from __future__ import annotations

from http import HTTPStatus
from typing import Any


def list_capabilities(service: Any) -> list[dict[str, Any]]:
    """List all registered capabilities."""
    return service._list_capabilities()


def get_capability(service: Any, capability_id: str) -> dict[str, Any]:
    """Get a single capability contract by ID."""
    return service._get_capability(capability_id)


def interpret_text(service: Any, request: dict[str, Any]) -> dict[str, Any]:
    """Interpret user text into capability/sequence intent."""
    return service._interpret_text(request)


def plan_intent(service: Any, request: dict[str, Any]) -> dict[str, Any]:
    """Plan capability execution from user intent."""
    return service._plan_intent(request)


def execute_capability(service: Any, request: dict[str, Any], event_callback: Any = None) -> dict[str, Any]:
    """Execute a capability by ID with inputs."""
    return service._execute_capability(request, event_callback)


def execute_capability_sync(service: Any, capability_id: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Synchronous capability execution (no streaming)."""
    return service._execute_capability_sync(capability_id, inputs)


def store_execution(service: Any, execution_response: dict[str, Any]) -> None:
    """Store an execution result."""
    return service._store_execution(execution_response)


def get_execution(service: Any, execution_id: str) -> dict[str, Any]:
    """Retrieve a stored execution."""
    return service._get_execution(execution_id)
