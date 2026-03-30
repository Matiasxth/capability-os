"""Growth route handlers: gaps, proposals, optimizations."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any


def _resp(code, data):
    from system.core.ui_bridge.api_server import APIResponse
    return APIResponse(code, data)


def pending_gaps(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, {"gaps": service.gap_analyzer.get_actionable_gaps()})


def analyze_gap(service: Any, payload: Any, gap_id: str = "", **kw: Any):
    return _resp(HTTPStatus.OK, service._analyze_gap(gap_id))


def generate_gap(service: Any, payload: Any, gap_id: str = "", **kw: Any):
    result = service._auto_generate_for_gap(gap_id)
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("growth_update", {"action": "gap_generated", "gap_id": gap_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, result)


def approve_gap(service: Any, payload: Any, gap_id: str = "", **kw: Any):
    result = service._approve_gap(gap_id)
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("growth_update", {"action": "gap_approved", "gap_id": gap_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, result)


def reject_gap(service: Any, payload: Any, gap_id: str = "", **kw: Any):
    return _resp(HTTPStatus.OK, service._reject_gap(gap_id))


def list_proposals(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, {"proposals": service.auto_install_pipeline.list_proposals()})


def regenerate_proposal(service: Any, payload: Any, prop_id: str = "", **kw: Any):
    return _resp(HTTPStatus.OK, service._regenerate_proposal(prop_id))


def approve_proposal(service: Any, payload: Any, cap_id: str = "", **kw: Any):
    result = service._approve_proposal(cap_id)
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("growth_update", {"action": "proposal_approved", "capability_id": cap_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, result)


def reject_proposal(service: Any, payload: Any, cap_id: str = "", **kw: Any):
    return _resp(HTTPStatus.OK, service._reject_proposal(cap_id))


def pending_optimizations(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, {"proposals": service.strategy_optimizer.get_optimization_proposals()})


def approve_optimization(service: Any, payload: Any, opt_id: str = "", **kw: Any):
    result = service._approve_optimization(opt_id, payload or {})
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("growth_update", {"action": "optimization_approved", "optimization_id": opt_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, result)


def reject_optimization(service: Any, payload: Any, opt_id: str = "", **kw: Any):
    return _resp(HTTPStatus.OK, service._reject_optimization(opt_id))
