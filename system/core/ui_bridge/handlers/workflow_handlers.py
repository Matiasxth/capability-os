"""Workflow route handlers: CRUD, execute, and layout persistence."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any


def _resp(code, data):
    from system.core.ui_bridge.api_server import APIResponse
    return APIResponse(code, data)


def _err(code, ec, msg):
    from system.core.ui_bridge.api_server import APIRequestError
    raise APIRequestError(code, ec, msg)


def list_workflows(service: Any, payload: Any, **kw: Any):
    """GET /workflows — list all workflows."""
    if not hasattr(service, "workflow_registry") or service.workflow_registry is None:
        return _resp(HTTPStatus.OK, {"workflows": []})
    return _resp(HTTPStatus.OK, {"workflows": service.workflow_registry.list()})


def create_workflow(service: Any, payload: Any, **kw: Any):
    """POST /workflows — create a new workflow."""
    if not hasattr(service, "workflow_registry") or service.workflow_registry is None:
        _err(HTTPStatus.SERVICE_UNAVAILABLE, "workflow_unavailable", "Workflow subsystem not available")
    body = payload or {}
    name = body.get("name", "").strip()
    if not name:
        _err(HTTPStatus.BAD_REQUEST, "missing_name", "Field 'name' is required.")
    wf = service.workflow_registry.create(
        name=name,
        description=body.get("description", ""),
        nodes=body.get("nodes"),
        edges=body.get("edges"),
    )
    return _resp(HTTPStatus.CREATED, {"status": "success", "workflow": wf})


def get_workflow(service: Any, payload: Any, wf_id: str = "", **kw: Any):
    """GET /workflows/{wf_id} — get a single workflow."""
    if not hasattr(service, "workflow_registry") or service.workflow_registry is None:
        _err(HTTPStatus.SERVICE_UNAVAILABLE, "workflow_unavailable", "Workflow subsystem not available")
    wf = service.workflow_registry.get(wf_id)
    if wf is None:
        _err(HTTPStatus.NOT_FOUND, "workflow_not_found", f"Workflow '{wf_id}' not found.")
    return _resp(HTTPStatus.OK, {"workflow": wf})


def update_workflow(service: Any, payload: Any, wf_id: str = "", **kw: Any):
    """PUT /workflows/{wf_id} — update workflow fields."""
    if not hasattr(service, "workflow_registry") or service.workflow_registry is None:
        _err(HTTPStatus.SERVICE_UNAVAILABLE, "workflow_unavailable", "Workflow subsystem not available")
    body = payload or {}
    fields = {}
    for key in ("name", "description", "nodes", "edges"):
        if key in body:
            fields[key] = body[key]
    wf = service.workflow_registry.update(wf_id, **fields)
    if wf is None:
        _err(HTTPStatus.NOT_FOUND, "workflow_not_found", f"Workflow '{wf_id}' not found.")
    return _resp(HTTPStatus.OK, {"status": "success", "workflow": wf})


def delete_workflow(service: Any, payload: Any, wf_id: str = "", **kw: Any):
    """DELETE /workflows/{wf_id} — delete a workflow."""
    if not hasattr(service, "workflow_registry") or service.workflow_registry is None:
        _err(HTTPStatus.SERVICE_UNAVAILABLE, "workflow_unavailable", "Workflow subsystem not available")
    removed = service.workflow_registry.delete(wf_id)
    if not removed:
        _err(HTTPStatus.NOT_FOUND, "workflow_not_found", f"Workflow '{wf_id}' not found.")
    return _resp(HTTPStatus.OK, {"status": "success", "removed": wf_id})


def run_workflow(service: Any, payload: Any, wf_id: str = "", **kw: Any):
    """POST /workflows/{wf_id}/run — execute a workflow and return results."""
    if not hasattr(service, "workflow_registry") or service.workflow_registry is None:
        _err(HTTPStatus.SERVICE_UNAVAILABLE, "workflow_unavailable", "Workflow subsystem not available")
    if not hasattr(service, "workflow_executor") or service.workflow_executor is None:
        _err(HTTPStatus.SERVICE_UNAVAILABLE, "executor_unavailable", "Workflow executor not available")
    wf = service.workflow_registry.get(wf_id)
    if wf is None:
        _err(HTTPStatus.NOT_FOUND, "workflow_not_found", f"Workflow '{wf_id}' not found.")
    result = service.workflow_executor.execute(wf)
    status_code = HTTPStatus.OK if result.get("status") == "success" else HTTPStatus.INTERNAL_SERVER_ERROR
    return _resp(status_code, result)


def save_layout(service: Any, payload: Any, wf_id: str = "", **kw: Any):
    """POST /workflows/{wf_id}/layout — save node positions and edges."""
    if not hasattr(service, "workflow_registry") or service.workflow_registry is None:
        _err(HTTPStatus.SERVICE_UNAVAILABLE, "workflow_unavailable", "Workflow subsystem not available")
    body = payload or {}
    nodes = body.get("nodes", [])
    edges = body.get("edges", [])
    wf = service.workflow_registry.save_layout(wf_id, nodes, edges)
    if wf is None:
        _err(HTTPStatus.NOT_FOUND, "workflow_not_found", f"Workflow '{wf_id}' not found.")
    return _resp(HTTPStatus.OK, {"status": "success", "workflow": wf})
