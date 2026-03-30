"""Supervisor API handlers — with full action execution."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any


def _resp(code, data):
    return type("R", (), {"status_code": code.value, "payload": data})()


# Pending previews awaiting approval
_pending_previews: dict[str, dict[str, Any]] = {}


def supervisor_status(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "supervisor"):
        return _resp(HTTPStatus.OK, {"running": False})
    return _resp(HTTPStatus.OK, service.supervisor.get_status())


def supervisor_log(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "supervisor"):
        return _resp(HTTPStatus.OK, {"log": []})
    return _resp(HTTPStatus.OK, {"log": service.supervisor.get_full_log()})


def supervisor_invoke_claude(service: Any, payload: Any, **kw: Any):
    """Chat with Claude Supervisor — uses mega-prompt and action system."""
    if not hasattr(service, "supervisor"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error", "error": "Supervisor not available"})

    prompt = (payload or {}).get("prompt", "")
    if not prompt:
        return _resp(HTTPStatus.BAD_REQUEST, {"status": "error", "error": "Field 'prompt' required"})

    # Build mega-prompt with system context
    from system.core.supervisor.supervisor_prompt import build_mega_prompt
    from system.core.supervisor.action_executor import (
        parse_action, classify_action, execute_auto, prepare_preview,
    )

    mega_prompt = build_mega_prompt(service)
    full_prompt = f"{mega_prompt}\n\nUser: {prompt}"

    # Get Claude's response
    response = service.supervisor.invoke_claude(full_prompt)

    # Parse action from response
    action = parse_action(response)
    if action is None:
        return _resp(HTTPStatus.OK, {"type": "text", "content": response})

    classification = classify_action(action)

    if classification == "auto":
        result = execute_auto(action)
        return _resp(HTTPStatus.OK, result)

    if classification in ("preview", "confirm"):
        preview = prepare_preview(action)
        # Store for approval
        preview_id = preview.get("preview_id", "")
        if preview_id:
            _pending_previews[preview_id] = {"action": action, "preview": preview}
            # Cleanup old previews (keep last 20)
            if len(_pending_previews) > 20:
                oldest = list(_pending_previews.keys())[0]
                del _pending_previews[oldest]
        return _resp(HTTPStatus.OK, preview)

    return _resp(HTTPStatus.OK, {"type": "text", "content": response})


def supervisor_approve(service: Any, payload: Any, **kw: Any):
    """Approve a pending preview action."""
    preview_id = (payload or {}).get("preview_id", "")
    if not preview_id or preview_id not in _pending_previews:
        return _resp(HTTPStatus.NOT_FOUND, {"status": "error", "error": "Preview not found or expired"})

    pending = _pending_previews.pop(preview_id)
    action = pending["action"]
    action_type = action.get("action", "")
    spec = action.get("spec", action)

    from system.core.supervisor.action_executor import execute_approved
    result = execute_approved(action_type, spec, service)

    # Emit event
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("supervisor_action", {"action": action_type, "result": result.get("status")})
    except Exception:
        pass

    return _resp(HTTPStatus.OK, result)


def supervisor_discard(service: Any, payload: Any, **kw: Any):
    """Discard a pending preview."""
    preview_id = (payload or {}).get("preview_id", "")
    _pending_previews.pop(preview_id, None)
    return _resp(HTTPStatus.OK, {"status": "discarded"})


def health_check_now(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "supervisor"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error"})
    results = service.supervisor.health_monitor.run_checks()
    return _resp(HTTPStatus.OK, {"checks": results, "status": service.supervisor.health_monitor.status})
