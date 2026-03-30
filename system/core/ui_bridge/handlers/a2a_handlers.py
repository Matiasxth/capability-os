"""A2A route handlers: agent card, task handling, agent management."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any


def _resp(code, data):
    from system.core.ui_bridge.api_server import APIResponse
    return APIResponse(code, data)


def agent_card(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, service.agent_card_builder.build())


def handle_task(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, service.a2a_server.handle_task(payload or {}))


def task_events(service: Any, payload: Any, task_id: str = "", **kw: Any):
    from system.core.ui_bridge.api_server import APIRequestError
    events = service.a2a_server.list_events(task_id)
    if events is None:
        raise APIRequestError(HTTPStatus.NOT_FOUND, "task_not_found", f"Task '{task_id}' not found.")
    return _resp(HTTPStatus.OK, {"task_id": task_id, "events": events})


def list_agents(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.a2a_service import a2a_list_agents
    return _resp(HTTPStatus.OK, {"agents": a2a_list_agents(service)})


def add_agent(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.a2a_service import a2a_add_agent
    result = a2a_add_agent(service, payload or {})
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("a2a_changed", {"action": "agent_added"})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, result)


def remove_agent(service: Any, payload: Any, agent_id: str = "", **kw: Any):
    from system.core.ui_bridge.a2a_service import a2a_remove_agent
    result = a2a_remove_agent(service, agent_id)
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("a2a_changed", {"action": "agent_removed", "agent_id": agent_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, result)


def delegate_task(service: Any, payload: Any, agent_id: str = "", **kw: Any):
    from system.core.ui_bridge.a2a_service import a2a_delegate
    result = a2a_delegate(service, agent_id, payload or {})
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("a2a_changed", {"action": "task_delegated", "agent_id": agent_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, result)
