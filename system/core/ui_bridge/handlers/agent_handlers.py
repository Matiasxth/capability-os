"""HTTP handlers for the /agent endpoint — agentic execution with SSE streaming."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any


def _resp(status: HTTPStatus, payload: dict[str, Any]):
    return type("R", (), {"status_code": status.value, "payload": payload})()


def start_agent(service: Any, payload: Any, **kw: Any):
    """Start an agent session. Returns initial events synchronously.
    For SSE streaming, use the /agent/stream endpoint.
    """
    if not hasattr(service, "agent_loop"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error", "error": "Agent not available"})

    message = (payload or {}).get("message", "")
    session_id = (payload or {}).get("session_id")
    history = (payload or {}).get("history", [])

    if not message:
        return _resp(HTTPStatus.BAD_REQUEST, {"status": "error", "error": "Field 'message' is required"})

    # Run agent loop and collect all events
    events = []
    result = None
    gen = service.agent_loop.run(message, session_id=session_id, conversation_history=history)
    try:
        for event in gen:
            events.append(event)
            # If awaiting confirmation, stop here
            if event.get("event") == "awaiting_confirmation":
                return _resp(HTTPStatus.OK, {
                    "status": "awaiting_confirmation",
                    "events": events,
                    "session_id": event.get("session_id") or (session_id or ""),
                    "confirmation": {
                        "confirmation_id": event["confirmation_id"],
                        "tool_id": event["tool_id"],
                        "params": event["params"],
                        "security_level": event["security_level"],
                        "description": event["description"],
                    },
                })
    except StopIteration as e:
        result = e.value

    # Extract final text from events
    final_text = ""
    for ev in reversed(events):
        if ev.get("event") == "agent_response":
            final_text = ev.get("text", "")
            break

    return _resp(HTTPStatus.OK, {
        "status": result.status if result else "complete",
        "events": events,
        "final_text": final_text or (result.final_text if result else ""),
        "session_id": result.session_id if result else session_id,
        "iteration_count": result.iteration_count if result else 0,
    })


def confirm_action(service: Any, payload: Any, **kw: Any):
    """Confirm or deny a pending Level 2/3 action."""
    if not hasattr(service, "agent_loop"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error", "error": "Agent not available"})

    session_id = kw.get("session_id", (payload or {}).get("session_id", ""))
    confirmation_id = (payload or {}).get("confirmation_id", "")
    approved = (payload or {}).get("approved", False)

    if not session_id or not confirmation_id:
        return _resp(HTTPStatus.BAD_REQUEST, {"status": "error", "error": "session_id and confirmation_id required"})

    events = []
    result = None
    gen = service.agent_loop.resume_after_confirmation(session_id, confirmation_id, approved)
    try:
        for event in gen:
            events.append(event)
            if event.get("event") == "awaiting_confirmation":
                return _resp(HTTPStatus.OK, {
                    "status": "awaiting_confirmation",
                    "events": events,
                    "session_id": session_id,
                    "confirmation": {
                        "confirmation_id": event["confirmation_id"],
                        "tool_id": event["tool_id"],
                        "params": event["params"],
                        "security_level": event["security_level"],
                        "description": event["description"],
                    },
                })
    except StopIteration as e:
        result = e.value

    final_text = ""
    for ev in reversed(events):
        if ev.get("event") == "agent_response":
            final_text = ev.get("text", "")
            break

    return _resp(HTTPStatus.OK, {
        "status": result.status if result else "complete",
        "events": events,
        "final_text": final_text or (result.final_text if result else ""),
        "session_id": session_id,
    })


def get_session(service: Any, payload: Any, **kw: Any):
    """Get current state of an agent session."""
    if not hasattr(service, "agent_loop"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error", "error": "Agent not available"})

    session_id = kw.get("session_id", "")
    session = service.agent_loop.get_session(session_id)
    if session is None:
        return _resp(HTTPStatus.NOT_FOUND, {"status": "error", "error": "Session not found"})

    return _resp(HTTPStatus.OK, session.to_dict())
