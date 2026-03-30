"""Slack Bot connector for Capability OS.

Uses only stdlib (urllib) — no external dependencies.
Polls conversations.history for incoming messages.
"""
from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from system.integrations.channel_adapter import (
    ChannelAdapter,
    ChannelError,
    ChannelPollingWorker,
    CHANNEL_BLOCKED_CAPABILITIES,
)

_SLACK_API = "https://slack.com/api"


class SlackConnectorError(ChannelError):
    """Structured error for Slack operations."""

    def __init__(self, message: str, error_code: str = "slack_error", details: dict[str, Any] | None = None):
        super().__init__(message, error_code, details)


class SlackConnector(ChannelAdapter):
    """Slack Web API connector with shared security layers."""

    # Block Slack's own capabilities from being triggered via Slack
    blocked_capabilities = CHANNEL_BLOCKED_CAPABILITIES | frozenset({
        "send_slack_message",
    })

    def __init__(
        self,
        bot_token: str = "",
        channel_id: str = "",
        allowed_user_ids: list[str] | None = None,
    ):
        super().__init__(allowed_user_ids=allowed_user_ids)
        self._bot_token = bot_token
        self._channel_id = channel_id
        self._bot_user_id: str | None = None

    def configure(self, **kwargs: Any) -> None:
        if "bot_token" in kwargs:
            self._bot_token = kwargs["bot_token"]
        if "channel_id" in kwargs:
            self._channel_id = kwargs["channel_id"]
        if "allowed_user_ids" in kwargs:
            self._allowed_user_ids = [str(i) for i in (kwargs["allowed_user_ids"] or [])]

    def validate(self) -> dict[str, Any]:
        try:
            result = self._api_call("auth.test")
            self._bot_user_id = result.get("user_id")
            return {"valid": True, "bot_name": result.get("user"), "team": result.get("team"), "bot_user_id": self._bot_user_id}
        except SlackConnectorError as exc:
            return {"valid": False, "error": str(exc)}

    def get_status(self) -> dict[str, Any]:
        configured = bool(self._bot_token)
        if not configured:
            return {"configured": False, "connected": False}
        v = self.validate()
        return {
            "configured": True,
            "connected": v.get("valid", False),
            "bot_name": v.get("bot_name"),
            "channel_id": self._channel_id or None,
            "allowed_user_ids": self._allowed_user_ids,
        }

    def send_message(self, channel_id: str, text: str, **kwargs: Any) -> dict[str, Any]:
        target = channel_id or self._channel_id
        if not target:
            raise SlackConnectorError("No channel_id provided and no default configured.", "no_channel")
        result = self._api_call("chat.postMessage", {"channel": target, "text": text})
        return {
            "status": "success",
            "message_id": result.get("ts"),
            "channel_id": target,
        }

    # ── Capability handler ──

    def send_slack_message(self, inputs: dict[str, Any]) -> dict[str, Any]:
        message = inputs.get("message", "")
        if not isinstance(message, str) or not message.strip():
            raise SlackConnectorError("Field 'message' is required.", "invalid_input")
        channel = inputs.get("channel_id") or self._channel_id
        return self.send_message(channel, message)

    # ── Internal HTTP ──

    def _api_call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._bot_token:
            raise SlackConnectorError("Bot token not configured.", "not_configured")
        url = f"{_SLACK_API}/{method}"
        data = json.dumps(params or {}).encode("utf-8")
        req = Request(url, data=data, headers={
            "Authorization": f"Bearer {self._bot_token}",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "CapabilityOS/1.0",
        })
        try:
            with urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:300]
            except Exception:
                pass
            raise SlackConnectorError(f"Slack API error: {detail or exc}", "api_error") from exc
        except URLError as exc:
            raise SlackConnectorError(f"Connection failed: {exc.reason}", "connection_error") from exc
        if not body.get("ok"):
            raise SlackConnectorError(body.get("error", "Unknown Slack error"), "api_error")
        return body


class SlackPollingWorker(ChannelPollingWorker):
    """Polls Slack conversations.history for new messages."""

    channel_name = "slack"
    poll_interval = 3.0

    def __init__(self, adapter: SlackConnector, **kwargs: Any):
        super().__init__(adapter, **kwargs)
        self._slack: SlackConnector = adapter
        self._last_ts: str = ""  # timestamp of last seen message

    def start(self) -> None:
        if not self._slack._bot_user_id:
            try:
                self._slack.validate()
            except Exception:
                pass
        # Initialize _last_ts to current time to avoid processing old messages
        if not self._last_ts:
            self._last_ts = str(time.time())
        super().start()

    def _fetch_updates(self) -> list[dict[str, Any]]:
        channel = self._slack._channel_id
        if not channel:
            return []
        try:
            result = self._slack._api_call("conversations.history", {
                "channel": channel,
                "oldest": self._last_ts,
                "limit": 10,
            })
        except SlackConnectorError:
            return []
        messages = result.get("messages", [])
        if messages:
            # Messages come newest-first, reverse to process oldest first
            messages = list(reversed(messages))
            self._last_ts = messages[-1].get("ts", self._last_ts)
        return messages

    def _extract_message(self, update: dict[str, Any]) -> tuple[str, str, str, str] | None:
        # Skip bot messages and subtypes (join, leave, etc.)
        if update.get("subtype"):
            return None
        if update.get("bot_id"):
            return None
        # Skip own messages
        user_id = update.get("user", "")
        if self._slack._bot_user_id and user_id == self._slack._bot_user_id:
            return None
        text = update.get("text", "").strip()
        if not text:
            return None
        channel = self._slack._channel_id or ""
        display_name = update.get("user", "SlackUser")
        return (channel, user_id, text, display_name)

    def _send_typing(self, channel_id: str) -> None:
        """Slack doesn't have a direct typing indicator in Web API."""
        pass
