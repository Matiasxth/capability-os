"""Capability route handlers: execute, plan, chat, interpret, list."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any


def _resp(code, data):
    from system.core.ui_bridge.api_server import APIResponse
    return APIResponse(code, data)


def _err(code, ec, msg):
    from system.core.ui_bridge.api_server import APIRequestError
    raise APIRequestError(code, ec, msg)


def list_capabilities(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.execution_service import list_capabilities as _list
    return _resp(HTTPStatus.OK, {"capabilities": _list(service)})


def get_capability(service: Any, payload: Any, capability_id: str = "", **kw: Any):
    from system.core.ui_bridge.execution_service import get_capability as _get
    return _resp(HTTPStatus.OK, {"capability": _get(service, capability_id)})


def capabilities_health(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, {"suggestions": service.performance_monitor.get_improvement_suggestions()})


def execute(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.execution_service import execute_capability
    return _resp(HTTPStatus.OK, execute_capability(service, payload or {}))


def chat(service: Any, payload: Any, **kw: Any):
    body = payload or {}
    message = body.get("message", "")
    user_name = body.get("user_name", "User")
    history = body.get("conversation_history") or []
    if not isinstance(message, str) or not message.strip():
        _err(HTTPStatus.BAD_REQUEST, "invalid_input", "A non-empty 'message' is required.")
    service._refresh_llm_client_settings()
    msg_type = service.intent_interpreter.classify_message(message, history)
    if msg_type == "conversational":
        response_text = service.intent_interpreter.chat_response(message, user_name, history)
        return _resp(HTTPStatus.OK, {"type": "chat", "response": response_text})
    suggested = None
    for msg in reversed(history):
        if msg.get("role") in ("assistant", "system") and msg.get("suggested_action"):
            suggested = msg["suggested_action"]
            break
    return _resp(HTTPStatus.OK, {"type": "action", "suggested_action": suggested})


def interpret(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.execution_service import interpret_text
    return _resp(HTTPStatus.OK, interpret_text(service, payload or {}))


def plan(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.execution_service import plan_intent
    return _resp(HTTPStatus.OK, plan_intent(service, payload or {}))


def get_execution(service: Any, payload: Any, execution_id: str = "", **kw: Any):
    from system.core.ui_bridge.execution_service import get_execution as _get_exec
    return _resp(HTTPStatus.OK, _get_exec(service, execution_id))


def get_execution_events(service: Any, payload: Any, execution_id: str = "", **kw: Any):
    from system.core.ui_bridge.execution_service import get_execution as _get_exec
    execution = _get_exec(service, execution_id)
    return _resp(HTTPStatus.OK, {"execution_id": execution_id, "events": execution["runtime"].get("logs", [])})
