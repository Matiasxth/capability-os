"""Tests for Discord Bot connector."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch, MagicMock
from typing import Any

from system.integrations.installed.discord_bot_connector import (
    DiscordConnector,
    DiscordConnectorError,
    DiscordPollingWorker,
)
from system.capabilities.implementations.discord_executor import DiscordCapabilityExecutor


class TestDiscordConnector(unittest.TestCase):

    def _mock_urlopen(self, response_body: dict | list):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_body).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_configure(self):
        c = DiscordConnector()
        c.configure(bot_token="discord-test", channel_id="123456", guild_id="G1", allowed_user_ids=["U1"])
        self.assertEqual(c._bot_token, "discord-test")
        self.assertEqual(c._channel_id, "123456")
        self.assertEqual(c._guild_id, "G1")

    def test_get_status_unconfigured(self):
        c = DiscordConnector()
        status = c.get_status()
        self.assertFalse(status["configured"])

    @patch("system.integrations.installed.discord_bot_connector.connector.urlopen")
    def test_validate_success(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_urlopen({"id": "BOT1", "username": "capos-bot"})
        c = DiscordConnector(bot_token="discord-test")
        result = c.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["bot_name"], "capos-bot")
        self.assertEqual(c._bot_user_id, "BOT1")

    @patch("system.integrations.installed.discord_bot_connector.connector.urlopen")
    def test_send_message(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_urlopen({"id": "msg123", "content": "hello"})
        c = DiscordConnector(bot_token="discord-test", channel_id="C1")
        result = c.send_message("C1", "Hello Discord!")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["message_id"], "msg123")

    def test_send_message_no_channel_raises(self):
        c = DiscordConnector(bot_token="discord-test")
        with self.assertRaises(DiscordConnectorError):
            c.send_message("", "hello")

    def test_send_message_no_token_raises(self):
        c = DiscordConnector()
        with self.assertRaises(DiscordConnectorError):
            c.send_message("C1", "hello")

    @patch("system.integrations.installed.discord_bot_connector.connector.urlopen")
    def test_send_discord_message_capability(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_urlopen({"id": "msg1"})
        c = DiscordConnector(bot_token="discord-test", channel_id="C1")
        result = c.send_discord_message({"message": "test"})
        self.assertEqual(result["status"], "success")

    def test_send_discord_message_empty_raises(self):
        c = DiscordConnector(bot_token="discord-test", channel_id="C1")
        with self.assertRaises(DiscordConnectorError):
            c.send_discord_message({"message": ""})

    def test_blocked_capabilities(self):
        c = DiscordConnector()
        self.assertEqual(c.check_capability_access("send_discord_message"), "blocked")
        self.assertEqual(c.check_capability_access("install_integration"), "blocked")
        self.assertEqual(c.check_capability_access("delete_file"), "confirm")
        self.assertEqual(c.check_capability_access("list_directory"), "allow")

    def test_authorization(self):
        c = DiscordConnector(allowed_user_ids=["U1"])
        ok, _ = c.is_authorized("U1")
        self.assertTrue(ok)
        ok, _ = c.is_authorized("U99")
        self.assertFalse(ok)


class TestDiscordPollingWorker(unittest.TestCase):

    def test_extract_message_normal(self):
        adapter = DiscordConnector(bot_token="test", channel_id="C1")
        worker = DiscordPollingWorker(adapter)
        result = worker._extract_message({
            "author": {"id": "U1", "username": "testuser"},
            "content": "hello",
            "channel_id": "C1",
        })
        self.assertIsNotNone(result)
        self.assertEqual(result[1], "U1")
        self.assertEqual(result[2], "hello")
        self.assertEqual(result[3], "testuser")

    def test_extract_message_skips_bots(self):
        adapter = DiscordConnector(bot_token="test", channel_id="C1")
        worker = DiscordPollingWorker(adapter)
        result = worker._extract_message({
            "author": {"id": "B1", "username": "bot", "bot": True},
            "content": "bot msg",
        })
        self.assertIsNone(result)

    def test_extract_message_skips_empty(self):
        adapter = DiscordConnector(bot_token="test", channel_id="C1")
        worker = DiscordPollingWorker(adapter)
        result = worker._extract_message({
            "author": {"id": "U1", "username": "u"},
            "content": "",
        })
        self.assertIsNone(result)

    def test_extract_message_skips_self(self):
        adapter = DiscordConnector(bot_token="test", channel_id="C1")
        adapter._bot_user_id = "BOT1"
        worker = DiscordPollingWorker(adapter)
        result = worker._extract_message({
            "author": {"id": "BOT1", "username": "bot"},
            "content": "my own msg",
        })
        self.assertIsNone(result)


class TestDiscordCapabilityExecutor(unittest.TestCase):

    def test_execute_unknown_capability(self):
        executor = DiscordCapabilityExecutor(connector=MagicMock())
        result = executor.execute("unknown_cap", {})
        self.assertIsNone(result)

    @patch("system.integrations.installed.discord_bot_connector.connector.urlopen")
    def test_execute_send_discord_message(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"id": "msg1"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        c = DiscordConnector(bot_token="test", channel_id="C1")
        executor = DiscordCapabilityExecutor(connector=c)
        result = executor.execute("send_discord_message", {"message": "hello"})
        self.assertEqual(result["status"], "success")

    def test_execute_no_connector(self):
        executor = DiscordCapabilityExecutor(connector=None)
        result = executor.execute("send_discord_message", {"message": "hello"})
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
