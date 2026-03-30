"""Scheduler API handlers: task CRUD, status, manual run."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any


def _resp(code, data):
    return type("R", (), {"status_code": code.value, "payload": data})()


def list_tasks(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "task_queue"):
        return _resp(HTTPStatus.OK, {"tasks": []})
    return _resp(HTTPStatus.OK, {"tasks": service.task_queue.list()})


def create_task(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "task_queue"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error", "error": "Scheduler not available"})
    p = payload or {}
    try:
        task = service.task_queue.add(
            description=p.get("description", ""),
            schedule=p.get("schedule", "daily_09:00"),
            action_type=p.get("action_type", "agent_message"),
            action_message=p.get("action_message", ""),
            agent_id=p.get("agent_id"),
            channel=p.get("channel"),
        )
        return _resp(HTTPStatus.CREATED, {"status": "success", "task": task})
    except ValueError as exc:
        return _resp(HTTPStatus.BAD_REQUEST, {"status": "error", "error": str(exc)})


def update_task(service: Any, payload: Any, task_id: str = "", **kw: Any):
    if not hasattr(service, "task_queue"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error"})
    try:
        task = service.task_queue.update(task_id, **(payload or {}))
        return _resp(HTTPStatus.OK, {"status": "success", "task": task})
    except (KeyError, ValueError) as exc:
        return _resp(HTTPStatus.BAD_REQUEST, {"status": "error", "error": str(exc)})


def delete_task(service: Any, payload: Any, task_id: str = "", **kw: Any):
    if not hasattr(service, "task_queue"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error"})
    service.task_queue.remove(task_id)
    return _resp(HTTPStatus.OK, {"status": "success", "removed": task_id})


def run_task_now(service: Any, payload: Any, task_id: str = "", **kw: Any):
    if not hasattr(service, "scheduler"):
        return _resp(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "error"})
    result = service.scheduler.run_task_now(task_id)
    return _resp(HTTPStatus.OK, result)


def scheduler_status(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "scheduler"):
        return _resp(HTTPStatus.OK, {"running": False})
    return _resp(HTTPStatus.OK, service.scheduler.get_status())


def scheduler_log(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "scheduler"):
        return _resp(HTTPStatus.OK, {"log": []})
    return _resp(HTTPStatus.OK, {"log": service.scheduler.execution_log})
