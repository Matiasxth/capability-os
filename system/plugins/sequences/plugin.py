"""Sequences plugin — provides capability sequence storage, registry,
and runner for multi-step execution flows.

Dependencies: capos.core.settings
"""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext
from system.sdk.contracts import (
    CapabilityEngineContract,
    CapabilityRegistryContract,
)

logger = logging.getLogger(__name__)


class SequencesPlugin:
    """Bootstraps SequenceStorage, SequenceRegistry, and SequenceRunner."""

    plugin_id: str = "capos.core.sequences"
    plugin_name: str = "Sequences"
    version: str = "1.0.0"
    dependencies: list[str] = ["capos.core.settings"]

    def __init__(self) -> None:
        self.sequence_storage: Any = None
        self.sequence_registry: Any = None
        self.sequence_runner: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, ctx: PluginContext) -> None:  # noqa: C901
        workspace_root = ctx.workspace_root
        capability_registry = ctx.get_optional(CapabilityRegistryContract)
        capability_engine = ctx.get_optional(CapabilityEngineContract)

        # --- SequenceStorage ---
        try:
            from system.core.sequences import SequenceStorage

            self.sequence_storage = SequenceStorage(
                workspace_root=workspace_root,
            )
            logger.info("Created SequenceStorage")
        except Exception:
            logger.exception("Failed to create SequenceStorage")

        # --- SequenceRegistry ---
        try:
            from system.core.sequences import SequenceRegistry

            if self.sequence_storage is not None:
                self.sequence_registry = SequenceRegistry(
                    storage=self.sequence_storage,
                )
                logger.info("Created SequenceRegistry")
        except Exception:
            logger.exception("Failed to create SequenceRegistry")

        # --- SequenceRunner ---
        try:
            from system.core.sequences import SequenceRunner

            if (
                self.sequence_registry is not None
                and capability_registry is not None
                and capability_engine is not None
            ):
                self.sequence_runner = SequenceRunner(
                    sequence_registry=self.sequence_registry,
                    capability_registry=capability_registry,
                    capability_engine=capability_engine,
                )
                logger.info("Created SequenceRunner")
            else:
                logger.warning(
                    "Missing dependencies for SequenceRunner — skipping"
                )
        except Exception:
            logger.exception("Failed to create SequenceRunner")

    def start(self) -> None:
        """Sequence subsystems are passive — nothing to start."""

    def stop(self) -> None:
        """Sequence subsystems are passive — nothing to stop."""


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def create_plugin() -> SequencesPlugin:
    """Entry-point factory used by the plugin loader."""
    return SequencesPlugin()
