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
    agent_id = (payload or {}).get("agent_id")

    # Load agent config if specified
    agent_config = None
    if agent_id and hasattr(service, "agent_registry"):
        agent_config = service.agent_registry.get(agent_id)

    if not message:
        return _resp(HTTPStatus.BAD_REQUEST, {"status": "error", "error": "Field 'message' is required"})

    # Run agent loop and collect all events
    events = []
    result = None
    gen = service.agent_loop.run(message, session_id=session_id, conversation_history=history, agent_config=agent_config)
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


# ── Agent Registry CRUD ──

def list_agents(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "agent_registry"):
        return _resp(HTTPStatus.OK, {"agents": []})
    return _resp(HTTPStatus.OK, {"agents": service.agent_registry.list()})


def create_agent(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "agent_registry"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error", "error": "Agent registry not available"})
    p = payload or {}
    try:
        agent = service.agent_registry.add(
            name=p.get("name", ""),
            emoji=p.get("emoji", "\U0001f916"),
            description=p.get("description", ""),
            system_prompt=p.get("system_prompt", ""),
            tool_ids=p.get("tool_ids"),
            llm_provider=p.get("llm_provider"),
            llm_model=p.get("llm_model"),
            security_level=p.get("security_level", "standard"),
            language=p.get("language", "auto"),
            max_iterations=p.get("max_iterations", 10),
        )
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("agent_changed", {"action": "created", "agent_id": agent.get("id", "")})
        return _resp(HTTPStatus.CREATED, {"status": "success", "agent": agent})
    except ValueError as exc:
        return _resp(HTTPStatus.BAD_REQUEST, {"status": "error", "error": str(exc)})


def get_agent_def(service: Any, payload: Any, agent_id: str = "", **kw: Any):
    if not hasattr(service, "agent_registry"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error", "error": "Agent registry not available"})
    agent = service.agent_registry.get(agent_id)
    if agent is None:
        return _resp(HTTPStatus.NOT_FOUND, {"status": "error", "error": f"Agent '{agent_id}' not found"})
    return _resp(HTTPStatus.OK, agent)


def update_agent(service: Any, payload: Any, agent_id: str = "", **kw: Any):
    if not hasattr(service, "agent_registry"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error", "error": "Agent registry not available"})
    try:
        agent = service.agent_registry.update(agent_id, **(payload or {}))
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("agent_changed", {"action": "updated", "agent_id": agent_id})
        return _resp(HTTPStatus.OK, {"status": "success", "agent": agent})
    except (KeyError, ValueError) as exc:
        return _resp(HTTPStatus.BAD_REQUEST, {"status": "error", "error": str(exc)})


def design_agent(service: Any, payload: Any, **kw: Any):
    """Ask the LLM to design an agent configuration from a description."""
    if not hasattr(service, "agent_loop"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error", "error": "Agent not available"})

    description = (payload or {}).get("description", "")
    if not description.strip():
        return _resp(HTTPStatus.BAD_REQUEST, {"status": "error", "error": "Field 'description' is required"})

    tool_list = [
        "filesystem_read_file", "filesystem_write_file", "filesystem_list_directory",
        "filesystem_create_directory", "filesystem_delete_file", "filesystem_copy_file",
        "filesystem_move_file", "filesystem_edit_file",
        "execution_run_command", "execution_run_script",
        "network_http_get", "network_extract_text", "network_extract_links",
        "browser_navigate", "browser_read_text", "browser_screenshot",
        "browser_click_element", "browser_type_text",
        "system_get_os_info", "system_get_workspace_info", "system_get_env_var",
    ]

    prompt = (
        f"Design an AI agent based on this description: {description}\n\n"
        f"Respond with ONLY a JSON object (no other text):\n"
        f'{{"name": "AgentName", "emoji": "emoji", "description": "what it does", '
        f'"system_prompt": "detailed personality and behavior instructions", '
        f'"tool_ids": ["tool1", "tool2"], "language": "auto", "max_iterations": 10}}\n\n'
        f"Available tools: {', '.join(tool_list)}\n"
        f"Choose only the tools relevant to this agent's purpose.\n"
        f"The system_prompt should be detailed (2-4 sentences) describing the agent's expertise and behavior."
    )

    try:
        llm = service.intent_interpreter.llm_client
        response = llm.complete(system_prompt="You are an agent designer. Return only valid JSON.", user_prompt=prompt)

        # Parse JSON from response
        import json as _json
        import re
        # Find JSON in response
        match = re.search(r'\{[\s\S]*\}', response)
        if match:
            config = _json.loads(match.group(0))
            # Validate tool_ids
            config["tool_ids"] = [t for t in (config.get("tool_ids") or []) if t in tool_list]
            return _resp(HTTPStatus.OK, {"status": "success", "config": config})
        return _resp(HTTPStatus.OK, {"status": "error", "error": "LLM did not return valid JSON", "raw": response[:500]})
    except Exception as exc:
        return _resp(HTTPStatus.OK, {"status": "error", "error": str(exc)})


def delete_agent(service: Any, payload: Any, agent_id: str = "", **kw: Any):
    if not hasattr(service, "agent_registry"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error", "error": "Agent registry not available"})
    try:
        service.agent_registry.remove(agent_id)
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("agent_changed", {"action": "deleted", "agent_id": agent_id})
        return _resp(HTTPStatus.OK, {"status": "success", "removed": agent_id})
    except ValueError as exc:
        return _resp(HTTPStatus.BAD_REQUEST, {"status": "error", "error": str(exc)})
