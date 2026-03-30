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
    from system.core.ui_bridge.growth_service import analyze_gap as _analyze
    return _resp(HTTPStatus.OK, _analyze(service, gap_id))


def generate_gap(service: Any, payload: Any, gap_id: str = "", **kw: Any):
    from system.core.ui_bridge.growth_service import auto_generate_for_gap
    result = auto_generate_for_gap(service, gap_id)
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("growth_update", {"action": "gap_generated", "gap_id": gap_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, result)


def approve_gap(service: Any, payload: Any, gap_id: str = "", **kw: Any):
    from system.core.ui_bridge.growth_service import approve_gap as _approve
    result = _approve(service, gap_id)
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("growth_update", {"action": "gap_approved", "gap_id": gap_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, result)


def reject_gap(service: Any, payload: Any, gap_id: str = "", **kw: Any):
    from system.core.ui_bridge.growth_service import reject_gap as _reject
    return _resp(HTTPStatus.OK, _reject(service, gap_id))


def list_proposals(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, {"proposals": service.auto_install_pipeline.list_proposals()})


def regenerate_proposal(service: Any, payload: Any, prop_id: str = "", **kw: Any):
    from system.core.ui_bridge.growth_service import regenerate_proposal as _regen
    return _resp(HTTPStatus.OK, _regen(service, prop_id))


def approve_proposal(service: Any, payload: Any, cap_id: str = "", **kw: Any):
    from system.core.ui_bridge.growth_service import approve_proposal as _appr
    result = _appr(service, cap_id)
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("growth_update", {"action": "proposal_approved", "capability_id": cap_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, result)


def reject_proposal(service: Any, payload: Any, cap_id: str = "", **kw: Any):
    from system.core.ui_bridge.growth_service import reject_proposal as _rej
    return _resp(HTTPStatus.OK, _rej(service, cap_id))


def pending_optimizations(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, {"proposals": service.strategy_optimizer.get_optimization_proposals()})


def approve_optimization(service: Any, payload: Any, opt_id: str = "", **kw: Any):
    from system.core.ui_bridge.growth_service import approve_optimization as _aopt
    result = _aopt(service, opt_id, payload or {})
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("growth_update", {"action": "optimization_approved", "optimization_id": opt_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, result)


def reject_optimization(service: Any, payload: Any, opt_id: str = "", **kw: Any):
    from system.core.ui_bridge.growth_service import reject_optimization as _ropt
    return _resp(HTTPStatus.OK, _ropt(service, opt_id))
