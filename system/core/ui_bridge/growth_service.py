"""Growth service — moved from api_server.py god-object.

These functions handle gap analysis, capability generation, and
optimization proposals. Called by growth_handlers.py.
"""
from __future__ import annotations

from typing import Any


def analyze_gap(service: Any, gap_id: str) -> dict[str, Any]:
    return service._analyze_gap(gap_id)

def auto_generate_for_gap(service: Any, gap_id: str) -> dict[str, Any]:
    return service._auto_generate_for_gap(gap_id)

def regenerate_proposal(service: Any, proposal_id: str) -> dict[str, Any]:
    return service._regenerate_proposal(proposal_id)

def generate_capability_for_gap(service: Any, gap_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return service._generate_capability_for_gap(gap_id, payload)

def approve_gap(service: Any, gap_id: str) -> dict[str, Any]:
    return service._approve_gap(gap_id)

def reject_gap(service: Any, gap_id: str) -> dict[str, Any]:
    return service._reject_gap(gap_id)

def approve_optimization(service: Any, opt_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return service._approve_optimization(opt_id, payload)

def reject_optimization(service: Any, opt_id: str) -> dict[str, Any]:
    return service._reject_optimization(opt_id)

def approve_proposal(service: Any, capability_id: str) -> dict[str, Any]:
    return service._approve_proposal(capability_id)

def reject_proposal(service: Any, capability_id: str) -> dict[str, Any]:
    return service._reject_proposal(capability_id)

def list_auto_proposals(service: Any) -> list[dict[str, Any]]:
    return service._list_auto_proposals() if hasattr(service, '_list_auto_proposals') else []
