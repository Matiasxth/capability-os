"""Detects capability gaps when the engine cannot resolve a user intent.

Per spec section 13.4 step 2: when the engine fails to find a capability,
the detector records the gap for the integration pipeline.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class IntegrationDetector:
    """Records and manages capability gaps detected during intent resolution."""

    def __init__(self) -> None:
        self._gaps: list[dict[str, Any]] = []

    def record_gap(
        self,
        intent: str,
        suggested_capability: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        gap: dict[str, Any] = {
            "id": f"gap_{uuid4().hex[:8]}",
            "intent": intent,
            "suggested_capability": suggested_capability,
            "context": deepcopy(context or {}),
            "detected_at": _now_iso(),
            "status": "open",
            "resolved_by": None,
        }
        self._gaps.append(gap)
        return deepcopy(gap)

    def list_gaps(self, status: str | None = None) -> list[dict[str, Any]]:
        if status is not None:
            return [deepcopy(g) for g in self._gaps if g["status"] == status]
        return [deepcopy(g) for g in self._gaps]

    def get_gap(self, gap_id: str) -> dict[str, Any] | None:
        for gap in self._gaps:
            if gap["id"] == gap_id:
                return deepcopy(gap)
        return None

    def resolve_gap(self, gap_id: str, integration_id: str) -> dict[str, Any] | None:
        for gap in self._gaps:
            if gap["id"] == gap_id:
                gap["status"] = "resolved"
                gap["resolved_by"] = integration_id
                return deepcopy(gap)
        return None

    def close_gap(self, gap_id: str, reason: str = "dismissed") -> dict[str, Any] | None:
        for gap in self._gaps:
            if gap["id"] == gap_id:
                gap["status"] = "closed"
                gap["resolved_by"] = reason
                return deepcopy(gap)
        return None

    @property
    def open_gap_count(self) -> int:
        return sum(1 for g in self._gaps if g["status"] == "open")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
