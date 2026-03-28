"""Classifies a capability gap into an integration type (spec section 13.3).

Integration types per spec:
  - web_app
  - rest_api
  - local_app
  - file_based

Uses keyword-scoring heuristics.  A future version may use the LLM for
higher-confidence classification.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

INTEGRATION_TYPES = {"web_app", "rest_api", "local_app", "file_based"}

_TYPE_KEYWORDS: dict[str, list[str]] = {
    "web_app": [
        "web", "browser", "website", "page", "whatsapp", "gmail",
        "twitter", "facebook", "slack", "notion", "trello",
    ],
    "rest_api": [
        "api", "rest", "endpoint", "http", "json", "webhook",
        "graphql", "oauth", "token", "request",
    ],
    "local_app": [
        "local", "desktop", "app", "native", "cli", "terminal",
        "executable", "installed", "process",
    ],
    "file_based": [
        "file", "csv", "excel", "pdf", "document", "import",
        "export", "xml", "yaml", "log",
    ],
}


class IntegrationClassifier:
    """Classifies a gap into one of the four integration types."""

    def classify(
        self,
        intent: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        intent_lower = intent.lower()
        scores: dict[str, int] = {}
        for itype, keywords in _TYPE_KEYWORDS.items():
            scores[itype] = sum(1 for kw in keywords if kw in intent_lower)

        best_type = max(scores, key=lambda k: scores[k])
        best_score = scores[best_type]

        if best_score == 0:
            best_type = "rest_api"  # default when no keywords match

        if best_score >= 2:
            confidence = "high"
        elif best_score >= 1:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "integration_type": best_type,
            "confidence": confidence,
            "scores": deepcopy(scores),
        }
