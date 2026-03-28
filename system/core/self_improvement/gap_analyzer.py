"""Analyzes accumulated capability gaps and surfaces actionable ones.

Spec section 14 rule: the system PROPOSES, the user APPROVES.
This module never installs or modifies anything — it only reads gap data
from the IntegrationDetector and marks frequently-occurring gaps as
*actionable* so the Approval API can present them for user confirmation.

A gap becomes actionable when the same ``suggested_capability`` has been
recorded **3 or more** times with status ``"open"``.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from system.integrations.classifier import IntegrationClassifier
from system.integrations.detector import IntegrationDetector


_ACTIONABLE_THRESHOLD = 3


class GapAnalyzer:
    """Reads IntegrationDetector gaps and surfaces actionable ones."""

    def __init__(
        self,
        detector: IntegrationDetector,
        classifier: IntegrationClassifier | None = None,
        threshold: int = _ACTIONABLE_THRESHOLD,
    ):
        self._detector = detector
        self._classifier = classifier or IntegrationClassifier()
        self._threshold = max(1, int(threshold))

    def get_actionable_gaps(self) -> list[dict[str, Any]]:
        """Return gaps that crossed the frequency threshold.

        Each item contains:
          - capability_id: the suggested_capability (or ``"unknown"``)
          - frequency: how many open gaps reference this capability
          - suggested_integration_type: classifier result
          - gap_ids: list of individual gap IDs contributing
        """
        open_gaps = self._detector.list_gaps(status="open")

        # Group by suggested_capability
        by_capability: dict[str, list[dict[str, Any]]] = {}
        for gap in open_gaps:
            cap_id = gap.get("suggested_capability") or "unknown"
            by_capability.setdefault(cap_id, []).append(gap)

        actionable: list[dict[str, Any]] = []
        for cap_id, gaps in sorted(by_capability.items()):
            if len(gaps) < self._threshold:
                continue

            # Use first gap's intent for classification
            first_intent = gaps[0].get("intent", "")
            classification = self._classifier.classify(first_intent)

            actionable.append({
                "capability_id": cap_id,
                "frequency": len(gaps),
                "suggested_integration_type": classification.get("integration_type", "rest_api"),
                "classification_confidence": classification.get("confidence", "low"),
                "gap_ids": [g["id"] for g in gaps],
                "sample_intent": first_intent,
            })

        return actionable

    @property
    def threshold(self) -> int:
        return self._threshold
