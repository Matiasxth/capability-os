"""Proposes an integration strategy from a classified gap (spec section 13.4 step 4).

Takes a gap record + classification and produces a plan that the
Template Engine and Generator can consume.
"""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


_DEFAULT_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "web_app": {"browser": True},
    "rest_api": {"auth": "api_key"},
    "local_app": {"executable": True},
    "file_based": {"workspace_access": True},
}


class IntegrationPlanner:
    """Produces a plan for a new integration from a gap and its classification."""

    def plan(
        self,
        gap: dict[str, Any],
        classification: dict[str, Any],
    ) -> dict[str, Any]:
        integration_type = classification.get("integration_type", "rest_api")
        intent = gap.get("intent", "")
        suggested = gap.get("suggested_capability")

        suggested_id = self._generate_id(intent, integration_type)
        capabilities = [suggested] if suggested else [f"{suggested_id}_action"]

        return {
            "integration_id": suggested_id,
            "integration_type": integration_type,
            "capabilities": capabilities,
            "requirements": deepcopy(_DEFAULT_REQUIREMENTS.get(integration_type, {})),
            "status": "proposed",
            "source_gap_id": gap.get("id"),
        }

    @staticmethod
    def _generate_id(intent: str, integration_type: str) -> str:
        """Generate an ID matching spec naming canon: ``provider_type_connector``.

        The manifest schema pattern is ``^[a-z0-9]+_[a-z0-9]+_connector$``.
        """
        tokens = re.sub(r"[^a-z0-9 ]+", "", intent.lower()).split()
        tokens = [t for t in tokens if len(t) > 2]
        provider = tokens[0] if tokens else "custom"
        type_token = {
            "web_app": "web",
            "rest_api": "api",
            "local_app": "local",
            "file_based": "file",
        }.get(integration_type, "custom")
        return f"{provider}_{type_token}_connector"
