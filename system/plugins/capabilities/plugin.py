"""Capabilities plugin — provides IntentInterpreter, LLMClient,
CapabilityEngine, PlanBuilder, and PlanValidator.

Publishes:
  - IntentInterpreterContract
  - LLMClientContract
  - CapabilityEngineContract

Dependencies: capos.core.settings
"""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext
from system.sdk.contracts import (
    CapabilityEngineContract,
    CapabilityRegistryContract,
    ExecutionHistoryContract,
    IntentInterpreterContract,
    LLMClientContract,
    MetricsCollectorContract,
    SemanticMemoryContract,
    SettingsProvider,
    ToolRuntimeContract,
)

logger = logging.getLogger(__name__)


class CapabilitiesPlugin:
    """Bootstraps interpretation, LLM access, planning, and execution engine."""

    plugin_id: str = "capos.core.capabilities"
    plugin_name: str = "Capabilities"
    version: str = "1.0.0"
    dependencies: list[str] = ["capos.core.settings"]

    def __init__(self) -> None:
        self.llm_client: Any = None
        self.intent_interpreter: Any = None
        self.capability_engine: Any = None
        self.plan_builder: Any = None
        self.plan_validator: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, ctx: PluginContext) -> None:  # noqa: C901
        settings = ctx.get_optional(SettingsProvider)
        capability_registry = ctx.get_optional(CapabilityRegistryContract)
        tool_runtime = ctx.get_optional(ToolRuntimeContract)

        # --- LLMClient ---
        try:
            from system.core.interpretation import LLMClient

            def _llm_settings() -> dict[str, Any]:
                if settings is None:
                    return {}
                try:
                    return settings.get_settings(mask_secrets=False).get("llm", {})
                except Exception:
                    return {}

            self.llm_client = LLMClient(settings_provider=_llm_settings)
            ctx.publish_service(LLMClientContract, self.llm_client)
            logger.info("Published LLMClientContract")
        except Exception:
            logger.exception("Failed to create LLMClient")

        # --- IntentInterpreter ---
        try:
            from system.core.interpretation import IntentInterpreter

            self.intent_interpreter = IntentInterpreter(
                capability_registry=capability_registry,
                llm_client=self.llm_client,
            )
            ctx.publish_service(IntentInterpreterContract, self.intent_interpreter)
            logger.info("Published IntentInterpreterContract")
        except Exception:
            logger.exception("Failed to create IntentInterpreter")

        # --- CapabilityEngine ---
        try:
            from system.core.capability_engine import CapabilityEngine

            metrics = ctx.get_optional(MetricsCollectorContract)
            execution_history = ctx.get_optional(ExecutionHistoryContract)
            semantic_memory = ctx.get_optional(SemanticMemoryContract)

            self.capability_engine = CapabilityEngine(
                capability_registry=capability_registry,
                tool_runtime=tool_runtime,
                metrics_collector=metrics,
                execution_history=execution_history,
                semantic_memory=semantic_memory,
            )
            ctx.publish_service(CapabilityEngineContract, self.capability_engine)
            logger.info("Published CapabilityEngineContract")
        except Exception:
            logger.exception("Failed to create CapabilityEngine")

        # --- PlanBuilder ---
        try:
            from system.core.planning import PlanBuilder

            self.plan_builder = PlanBuilder()
            logger.info("Created PlanBuilder")
        except Exception:
            logger.exception("Failed to create PlanBuilder")

        # --- PlanValidator ---
        try:
            from system.core.planning import PlanValidator

            self.plan_validator = PlanValidator(
                capability_registry=capability_registry,
            )
            logger.info("Created PlanValidator")
        except Exception:
            logger.exception("Failed to create PlanValidator")

    def start(self) -> None:
        """Capability subsystems are passive — nothing to start."""

    def stop(self) -> None:
        """Capability subsystems are passive — nothing to stop."""


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def create_plugin() -> CapabilitiesPlugin:
    """Entry-point factory used by the plugin loader."""
    return CapabilitiesPlugin()
