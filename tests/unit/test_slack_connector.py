"""Tests for Slack Bot connector."""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch, MagicMock
from typing import Any

from system.integrations.installed.slack_bot_connector import (
    SlackConnector,
    SlackConnectorError,
    SlackPollingWorker,
)
from system.capabilities.implementations.slack_executor import SlackCapabilityExecutor


class TestSlackConnector(unittest.TestCase):

    def _mock_urlopen(self, response_body: dict):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(response_body).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_configure(self):
        c = SlackConnector()
        c.configure(bot_token="xoxb-test", channel_id="C123", allowed_user_ids=["U1"])
        self.assertEqual(c._bot_token, "xoxb-test")
        self.assertEqual(c._channel_id, "C123")
        self.assertEqual(c._allowed_user_ids, ["U1"])

    def test_get_status_unconfigured(self):
        c = SlackConnector()
        status = c.get_status()
        self.assertFalse(status["configured"])

    @patch("system.integrations.installed.slack_bot_connector.connector.urlopen")
    def test_validate_success(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_urlopen({"ok": True, "user": "capos-bot", "user_id": "U999", "team": "TestTeam"})
        c = SlackConnector(bot_token="xoxb-test")
        result = c.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["bot_name"], "capos-bot")
        self.assertEqual(c._bot_user_id, "U999")

    @patch("system.integrations.installed.slack_bot_connector.connector.urlopen")
    def test_send_message(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_urlopen({"ok": True, "ts": "1234567890.123456"})
        c = SlackConnector(bot_token="xoxb-test", channel_id="C123")
        result = c.send_message("C123", "Hello Slack!")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["message_id"], "1234567890.123456")

    def test_send_message_no_channel_raises(self):
        c = SlackConnector(bot_token="xoxb-test")
        with self.assertRaises(SlackConnectorError):
            c.send_message("", "hello")

    def test_send_message_no_token_raises(self):
        c = SlackConnector()
        with self.assertRaises(SlackConnectorError):
            c.send_message("C123", "hello")

    @patch("system.integrations.installed.slack_bot_connector.connector.urlopen")
    def test_send_slack_message_capability(self, mock_urlopen):
        mock_urlopen.return_value = self._mock_urlopen({"ok": True, "ts": "123"})
        c = SlackConnector(bot_token="xoxb-test", channel_id="C123")
        result = c.send_slack_message({"message": "test"})
        self.assertEqual(result["status"], "success")

    def test_send_slack_message_empty_raises(self):
        c = SlackConnector(bot_token="xoxb-test", channel_id="C123")
        with self.assertRaises(SlackConnectorError):
            c.send_slack_message({"message": ""})

    def test_blocked_capabilities(self):
        c = SlackConnector()
        self.assertEqual(c.check_capability_access("send_slack_message"), "blocked")
        self.assertEqual(c.check_capability_access("install_integration"), "blocked")
        self.assertEqual(c.check_capability_access("delete_file"), "confirm")
        self.assertEqual(c.check_capability_access("list_directory"), "allow")

    def test_authorization(self):
        c = SlackConnector(allowed_user_ids=["U1", "U2"])
        ok, _ = c.is_authorized("U1")
        self.assertTrue(ok)
        ok, _ = c.is_authorized("U99")
        self.assertFalse(ok)


class TestSlackPollingWorker(unittest.TestCase):

    def test_extract_message_normal(self):
        adapter = SlackConnector(bot_token="xoxb-test", channel_id="C123")
        worker = SlackPollingWorker(adapter)
        result = worker._extract_message({"user": "U1", "text": "hello", "ts": "123"})
        self.assertIsNotNone(result)
        self.assertEqual(result[1], "U1")  # user_id
        self.assertEqual(result[2], "hello")  # text

    def test_extract_message_skips_bots(self):
        adapter = SlackConnector(bot_token="xoxb-test", channel_id="C123")
        worker = SlackPollingWorker(adapter)
        result = worker._extract_message({"bot_id": "B1", "text": "bot msg"})
        self.assertIsNone(result)

    def test_extract_message_skips_subtypes(self):
        adapter = SlackConnector(bot_token="xoxb-test", channel_id="C123")
        worker = SlackPollingWorker(adapter)
        result = worker._extract_message({"subtype": "channel_join", "user": "U1", "text": "joined"})
        self.assertIsNone(result)

    def test_extract_message_skips_empty(self):
        adapter = SlackConnector(bot_token="xoxb-test", channel_id="C123")
        worker = SlackPollingWorker(adapter)
        result = worker._extract_message({"user": "U1", "text": ""})
        self.assertIsNone(result)


class TestSlackCapabilityExecutor(unittest.TestCase):

    def test_execute_unknown_capability(self):
        executor = SlackCapabilityExecutor(connector=MagicMock())
        result = executor.execute("unknown_cap", {})
        self.assertIsNone(result)

    @patch("system.integrations.installed.slack_bot_connector.connector.urlopen")
    def test_execute_send_slack_message(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"ok": True, "ts": "1"}).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        c = SlackConnector(bot_token="xoxb-test", channel_id="C123")
        executor = SlackCapabilityExecutor(connector=c)
        result = executor.execute("send_slack_message", {"message": "hello"})
        self.assertEqual(result["status"], "success")

    def test_execute_no_connector(self):
        executor = SlackCapabilityExecutor(connector=None)
        result = executor.execute("send_slack_message", {"message": "hello"})
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
