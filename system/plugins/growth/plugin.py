"""Growth plugin — provides the self-improvement pipeline: gap analysis,
capability generation, auto-install, strategy optimization, performance
monitoring, and runtime analysis.

Dependencies: capos.core.settings, capos.core.capabilities
"""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext
from system.sdk.contracts import (
    CapabilityRegistryContract,
    LLMClientContract,
    MetricsCollectorContract,
    ToolRegistryContract,
    ToolRuntimeContract,
)

logger = logging.getLogger(__name__)


class GrowthPlugin:
    """Bootstraps the full self-improvement pipeline."""

    plugin_id: str = "capos.core.growth"
    plugin_name: str = "Growth"
    version: str = "1.0.0"
    dependencies: list[str] = ["capos.core.settings", "capos.core.capabilities"]

    def __init__(self) -> None:
        self.gap_analyzer: Any = None
        self.capability_generator: Any = None
        self.auto_install_pipeline: Any = None
        self.strategy_optimizer: Any = None
        self.performance_monitor: Any = None
        self.runtime_analyzer: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, ctx: PluginContext) -> None:  # noqa: C901
        workspace_root = ctx.workspace_root
        capability_registry = ctx.get_optional(CapabilityRegistryContract)
        tool_registry = ctx.get_optional(ToolRegistryContract)
        tool_runtime = ctx.get_optional(ToolRuntimeContract)
        metrics_collector = ctx.get_optional(MetricsCollectorContract)
        llm_client = ctx.get_optional(LLMClientContract)

        proposals_dir = workspace_root / "proposals"

        # --- RuntimeAnalyzer ---
        try:
            from system.core.self_improvement import RuntimeAnalyzer

            self.runtime_analyzer = RuntimeAnalyzer(tool_registry=tool_registry)
            logger.info("Created RuntimeAnalyzer")
        except Exception:
            logger.exception("Failed to create RuntimeAnalyzer")

        # --- PerformanceMonitor ---
        try:
            from system.core.self_improvement import PerformanceMonitor

            if metrics_collector is not None:
                self.performance_monitor = PerformanceMonitor(
                    metrics_collector=metrics_collector,
                )
                logger.info("Created PerformanceMonitor")
            else:
                logger.warning(
                    "MetricsCollector not available — skipping PerformanceMonitor"
                )
        except Exception:
            logger.exception("Failed to create PerformanceMonitor")

        # --- GapAnalyzer ---
        try:
            from system.core.self_improvement import GapAnalyzer
            from system.integrations.detector.integration_detector import (
                IntegrationDetector,
            )

            detector = IntegrationDetector()
            self.gap_analyzer = GapAnalyzer(detector=detector)
            logger.info("Created GapAnalyzer")
        except Exception:
            logger.exception("Failed to create GapAnalyzer")

        # --- CapabilityGenerator ---
        try:
            from system.core.self_improvement import CapabilityGenerator

            if llm_client is not None and capability_registry is not None:
                self.capability_generator = CapabilityGenerator(
                    llm_client=llm_client,
                    capability_registry=capability_registry,
                    proposals_dir=proposals_dir,
                )
                logger.info("Created CapabilityGenerator")
            else:
                logger.warning(
                    "LLMClient or CapabilityRegistry not available — "
                    "skipping CapabilityGenerator"
                )
        except Exception:
            logger.exception("Failed to create CapabilityGenerator")

        # --- StrategyOptimizer ---
        try:
            from system.core.self_improvement import StrategyOptimizer

            if self.performance_monitor is not None and capability_registry is not None:
                self.strategy_optimizer = StrategyOptimizer(
                    performance_monitor=self.performance_monitor,
                    capability_registry=capability_registry,
                )
                logger.info("Created StrategyOptimizer")
            else:
                logger.warning(
                    "PerformanceMonitor or CapabilityRegistry not available — "
                    "skipping StrategyOptimizer"
                )
        except Exception:
            logger.exception("Failed to create StrategyOptimizer")

        # --- AutoInstallPipeline ---
        try:
            from system.core.self_improvement import (
                AutoInstallPipeline,
                ToolCodeGenerator,
                ToolValidator,
            )

            if (
                self.runtime_analyzer is not None
                and self.capability_generator is not None
                and tool_registry is not None
                and tool_runtime is not None
                and capability_registry is not None
            ):
                from system.core.self_improvement.python_sandbox import PythonSandbox
                from system.core.self_improvement.nodejs_sandbox import NodejsSandbox
                llm = ctx.get_optional(LLMClientContract)
                tool_code_gen = ToolCodeGenerator(llm_client=llm)
                tool_validator = ToolValidator(
                    python_sandbox=PythonSandbox(ctx.workspace_root / "sandbox" / "py"),
                    nodejs_sandbox=NodejsSandbox(ctx.workspace_root / "sandbox" / "js"),
                    llm_client=llm,
                )

                self.auto_install_pipeline = AutoInstallPipeline(
                    runtime_analyzer=self.runtime_analyzer,
                    capability_generator=self.capability_generator,
                    tool_code_generator=tool_code_gen,
                    tool_validator=tool_validator,
                    tool_registry=tool_registry,
                    tool_runtime=tool_runtime,
                    capability_registry=capability_registry,
                    proposals_dir=proposals_dir,
                )
                logger.info("Created AutoInstallPipeline")
            else:
                logger.warning(
                    "Missing dependencies for AutoInstallPipeline — skipping"
                )
        except Exception:
            logger.exception("Failed to create AutoInstallPipeline")

    def start(self) -> None:
        """Growth subsystems are passive — nothing to start."""

    def stop(self) -> None:
        """Growth subsystems are passive — nothing to stop."""


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def create_plugin() -> GrowthPlugin:
    """Entry-point factory used by the plugin loader."""
    return GrowthPlugin()
