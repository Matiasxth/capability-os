#!/usr/bin/env python3
"""Slack channel worker — runs as separate process."""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def main() -> None:
    from system.workers.channel_worker import ChannelWorkerBase

    class SlackWorker(ChannelWorkerBase):
        worker_name = "slack_worker"
        channel_name = "slack"
        poll_interval = 3.0
        pool_size = 4

        def __init__(self) -> None:
            super().__init__()
            self._polling_worker: Any = None

        def create_connector(self, settings: dict) -> Any:
            from system.integrations.installed.slack_bot_connector.connector import SlackConnector
            sl_settings = settings.get("slack", {})
            bot_token = sl_settings.get("bot_token", "")
            if not bot_token:
                logger.warning("No Slack bot_token configured")
                return None
            connector = SlackConnector(
                bot_token=bot_token,
                channel_id=sl_settings.get("channel_id", ""),
                allowed_user_ids=sl_settings.get("allowed_user_ids", []),
            )
            return connector

        def run(self) -> None:
            settings = self.load_settings()

            self._connector = self.create_connector(settings)
            if self._connector is None:
                return

            self.setup_interpreter(settings)

            from system.integrations.installed.slack_bot_connector.connector import SlackPollingWorker
            self._polling_worker = SlackPollingWorker(
                adapter=self._connector,
                interpreter=self._interpreter,
                executor=None,
                execution_history=None,
            )

            original_handle = self._polling_worker._handle_message

            def threaded_handle(channel_id, text, user_name):
                self._pool.submit(original_handle, channel_id, text, user_name)

            self._polling_worker._handle_message = threaded_handle

            logger.info("Slack worker started")
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
            logger.info("Slack worker stopped")

    worker = SlackWorker()
    worker.bootstrap()
    worker.run()
    worker.shutdown()


if __name__ == "__main__":
    main()
