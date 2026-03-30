"""A2A service — moved from api_server.py god-object.

These functions handle Agent-to-Agent protocol operations.
Called by a2a_handlers.py.
"""
from __future__ import annotations

from typing import Any


def a2a_list_agents(service: Any) -> list[dict[str, Any]]:
    return service._a2a_list_agents()

def a2a_add_agent(service: Any, payload: dict[str, Any]) -> dict[str, Any]:
    return service._a2a_add_agent(payload)

def a2a_remove_agent(service: Any, agent_id: str) -> dict[str, Any]:
    return service._a2a_remove_agent(agent_id)

def a2a_delegate(service: Any, agent_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return service._a2a_delegate(agent_id, payload)
