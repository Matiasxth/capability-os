#!/usr/bin/env python3
"""Discord channel worker — runs as separate process."""
from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def main() -> None:
    from system.workers.channel_worker import ChannelWorkerBase

    class DiscordWorker(ChannelWorkerBase):
        worker_name = "discord_worker"
        channel_name = "discord"
        poll_interval = 3.0
        pool_size = 4

        def __init__(self) -> None:
            super().__init__()
            self._polling_worker: Any = None

        def create_connector(self, settings: dict) -> Any:
            from system.integrations.installed.discord_bot_connector.connector import DiscordConnector
            dc_settings = settings.get("discord", {})
            bot_token = dc_settings.get("bot_token", "")
            if not bot_token:
                logger.warning("No Discord bot_token configured")
                return None
            connector = DiscordConnector(
                bot_token=bot_token,
                channel_id=dc_settings.get("channel_id", ""),
                guild_id=dc_settings.get("guild_id", ""),
                allowed_user_ids=dc_settings.get("allowed_user_ids", []),
            )
            return connector

        def run(self) -> None:
            settings = self.load_settings()

            self._connector = self.create_connector(settings)
            if self._connector is None:
                return

            self.setup_interpreter(settings)

            from system.integrations.installed.discord_bot_connector.connector import DiscordPollingWorker
            self._polling_worker = DiscordPollingWorker(
                adapter=self._connector,
                interpreter=self._interpreter,
                executor=None,
                execution_history=None,
            )

            original_handle = self._polling_worker._handle_message

            def threaded_handle(channel_id, text, user_name):
                self._pool.submit(original_handle, channel_id, text, user_name)

            self._polling_worker._handle_message = threaded_handle

            logger.info("Discord worker started")
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
            logger.info("Discord worker stopped")

    worker = DiscordWorker()
    worker.bootstrap()
    worker.run()
    worker.shutdown()


if __name__ == "__main__":
    main()
