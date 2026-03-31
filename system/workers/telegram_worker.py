#!/usr/bin/env python3
"""Telegram channel worker — runs as separate process.

Polls Telegram Bot API, processes messages in thread pool,
publishes events to Redis. Main process stays responsive.
"""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def main() -> None:
    from system.workers.channel_worker import ChannelWorkerBase

    class TelegramWorker(ChannelWorkerBase):
        worker_name = "telegram_worker"
        channel_name = "telegram"
        poll_interval = 3.0
        pool_size = 4

        def __init__(self) -> None:
            super().__init__()
            self._polling_worker: Any = None

        def create_connector(self, settings: dict) -> Any:
            from system.integrations.installed.telegram_bot_connector.connector import TelegramConnector
            tg_settings = settings.get("telegram", {})
            bot_token = tg_settings.get("bot_token", "")
            if not bot_token:
                logger.warning("No Telegram bot_token configured")
                return None
            connector = TelegramConnector(
                bot_token=bot_token,
                default_chat_id=tg_settings.get("default_chat_id", ""),
                allowed_user_ids=tg_settings.get("allowed_user_ids", []),
            )
            return connector

        def run(self) -> None:
            settings = self.load_settings()

            self._connector = self.create_connector(settings)
            if self._connector is None:
                return

            self.setup_interpreter(settings)

            # Create polling worker using existing ChannelPollingWorker
            from system.integrations.installed.telegram_bot_connector.connector import TelegramPollingWorker
            self._polling_worker = TelegramPollingWorker(
                connector=self._connector,
                interpreter=self._interpreter,
                executor=None,  # TODO: wire executor via Redis
                execution_history=None,
            )

            # Override the polling worker's _handle_message to run in thread pool
            original_handle = self._polling_worker._handle_message

            def threaded_handle(channel_id, text, user_name):
                self._pool.submit(original_handle, channel_id, text, user_name)

            self._polling_worker._handle_message = threaded_handle

            # Run the poll loop
            logger.info("Telegram worker started (threaded message processing)")
            self._polling_worker._running = True
            while self._running:
                try:
                    self.heartbeat()
                    updates = self._polling_worker._fetch_updates()
                    for u in updates:
                        try:
                            self._polling_worker._process_update(u)
                        except Exception as exc:
                            logger.error("Process update error: %s", exc)
                except Exception as exc:
                    logger.error("Poll error: %s", exc)
                time.sleep(self.poll_interval)

            self._polling_worker._running = False
            logger.info("Telegram worker stopped")

    worker = TelegramWorker()
    worker.bootstrap()
    worker.run()
    worker.shutdown()


if __name__ == "__main__":
    main()
