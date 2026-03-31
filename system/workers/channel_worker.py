"""Generic channel polling worker — runs as separate process.

Polls a messaging channel API, processes messages in a thread pool
(so polling never blocks on LLM), and publishes events to Redis.

Subclasses implement:
- create_connector() → ChannelAdapter
- create_polling_worker() → ChannelPollingWorker
"""
from __future__ import annotations

import logging
import time
from typing import Any

from system.workers.base import BaseWorker

logger = logging.getLogger(__name__)


class ChannelWorkerBase(BaseWorker):
    """Base for channel polling workers running in separate processes."""

    channel_name: str = "channel"
    poll_interval: float = 3.0

    def __init__(self) -> None:
        super().__init__()
        self._connector: Any = None
        self._interpreter: Any = None
        self._executor: Any = None

    def create_connector(self, settings: dict) -> Any:
        """Create the channel-specific connector. Override in subclass."""
        raise NotImplementedError

    def setup_interpreter(self, settings: dict) -> None:
        """Set up LLM interpreter and executor from settings."""
        try:
            from system.core.interpretation.llm_client import LLMClient
            from system.core.interpretation.intent_interpreter import IntentInterpreter

            llm_config = settings.get("llm", {})
            llm = LLMClient(
                provider=llm_config.get("provider", "ollama"),
                base_url=llm_config.get("base_url", "http://localhost:11434"),
                api_key=llm_config.get("api_key", ""),
                model=llm_config.get("model", ""),
                timeout_ms=llm_config.get("timeout_ms", 30000),
            )
            self._interpreter = IntentInterpreter(llm)
            logger.info("LLM interpreter ready (%s/%s)", llm_config.get("provider"), llm_config.get("model"))
        except Exception as exc:
            logger.warning("LLM interpreter not available: %s", exc)
            self._interpreter = None

    def run(self) -> None:
        """Main polling loop."""
        settings = self.load_settings()
        channel_settings = settings.get(self.channel_name, {})

        # Create connector
        self._connector = self.create_connector(settings)
        if self._connector is None:
            logger.error("Failed to create connector — exiting")
            return

        # Set up interpreter
        self.setup_interpreter(settings)

        logger.info("Starting %s polling (interval=%.1fs)", self.channel_name, self.poll_interval)
        while self._running:
            try:
                self.heartbeat()
                self.poll_cycle()
            except Exception as exc:
                logger.error("Poll cycle error: %s", exc)
                # Publish error event
                if self._queue:
                    try:
                        self._queue.publish(f"capos:events:error", {
                            "type": "error",
                            "data": {"source": f"{self.channel_name}_worker", "message": str(exc)[:300]},
                        })
                    except Exception:
                        pass
            time.sleep(self.poll_interval)

        logger.info("%s polling stopped", self.channel_name)

    def poll_cycle(self) -> None:
        """Single poll iteration. Override for custom behavior."""
        # Default: delegate to the connector's polling worker if it has one
        pass
