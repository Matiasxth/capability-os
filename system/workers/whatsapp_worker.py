#!/usr/bin/env python3
"""WhatsApp reply worker — runs as separate process.

Subscribes to whatsapp_message events via Redis, processes messages
in a thread pool (interpret → execute → reply), publishes results back.

The WhatsApp backend manager (Browser/Baileys/Official) stays in the
main process. This worker only handles the reply pipeline.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def main() -> None:
    from system.workers.base import BaseWorker

    class WhatsAppWorker(BaseWorker):
        worker_name = "whatsapp_worker"
        pool_size = 4

        def __init__(self) -> None:
            super().__init__()
            self._interpreter: Any = None

        def run(self) -> None:
            settings = self.load_settings()

            # Set up LLM interpreter
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
                logger.info("LLM interpreter ready")
            except Exception as exc:
                logger.warning("LLM interpreter not available: %s", exc)
                self._interpreter = None

            if self._interpreter is None:
                logger.error("Cannot start without interpreter — exiting")
                return

            # Subscribe to WhatsApp messages via Redis
            logger.info("WhatsApp reply worker started — listening for messages")
            try:
                for event in self._queue.subscribe("capos:events:whatsapp_message"):
                    if not self._running:
                        break
                    self.heartbeat()
                    # Process in thread pool (non-blocking)
                    self._pool.submit(self._handle_event, event)
            except Exception as exc:
                if self._running:
                    logger.error("Subscribe error: %s", exc)

            logger.info("WhatsApp reply worker stopped")

        def _handle_event(self, event: dict) -> None:
            """Process a single WhatsApp message event."""
            try:
                data = event.get("data", event)
                text = data.get("text", "")
                from_user = data.get("from", data.get("pushName", ""))
                channel_id = data.get("channel_id", from_user)

                if not text.strip():
                    return

                logger.info("Processing message from %s: %s", from_user, text[:50])

                # Classify and respond
                msg_type = self._interpreter.classify_message(text)
                if msg_type == "conversational":
                    response = self._interpreter.chat_response(text, from_user)
                else:
                    interpretation = self._interpreter.interpret(text)
                    suggestion = interpretation.get("suggestion", {})
                    if suggestion.get("type") == "unknown":
                        response = "I didn't understand that. Can you be more specific?"
                    else:
                        response = f"Understood: {suggestion.get('capability', 'action')} — processing..."

                # Publish reply back via Redis for main process to send
                self._queue.push("capos:whatsapp:replies", {
                    "channel_id": channel_id,
                    "text": response,
                    "from_user": from_user,
                })

            except Exception as exc:
                logger.error("Handle event error: %s", exc)

    worker = WhatsAppWorker()
    worker.bootstrap()
    worker.run()
    worker.shutdown()


if __name__ == "__main__":
    main()
