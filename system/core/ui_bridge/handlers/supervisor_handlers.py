"""Supervisor API handlers."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any


def _resp(code, data):
    return type("R", (), {"status_code": code.value, "payload": data})()


def supervisor_status(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "supervisor"):
        return _resp(HTTPStatus.OK, {"running": False})
    return _resp(HTTPStatus.OK, service.supervisor.get_status())


def supervisor_log(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "supervisor"):
        return _resp(HTTPStatus.OK, {"log": []})
    return _resp(HTTPStatus.OK, {"log": service.supervisor.get_full_log()})


def supervisor_invoke_claude(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "supervisor"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error", "error": "Supervisor not available"})
    prompt = (payload or {}).get("prompt", "")
    if not prompt:
        return _resp(HTTPStatus.BAD_REQUEST, {"status": "error", "error": "Field 'prompt' required"})

    # Add system context so Claude knows what CapOS is
    context = (
        "You are the Supervisor of Capability OS, an AI-powered personal OS. "
        "The system has: 40+ tools (filesystem, browser, network, execution), "
        "custom agents, project workspaces, WhatsApp/Telegram/Slack/Discord channels, "
        "progressive security (3 levels), hot-reload skills, and a scheduler. "
        "Respond concisely in the user's language. "
        f"User asks: {prompt}"
    )
    response = service.supervisor.invoke_claude(context)
    return _resp(HTTPStatus.OK, {"status": "success", "response": response})


def health_check_now(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "supervisor"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error"})
    results = service.supervisor.health_monitor.run_checks()
    return _resp(HTTPStatus.OK, {"checks": results, "status": service.supervisor.health_monitor.status})
