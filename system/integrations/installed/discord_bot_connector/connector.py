"""Discord Bot connector for Capability OS.

Uses only stdlib (urllib) — no external dependencies.
Polls channel messages via Discord HTTP API v10.
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

_DISCORD_API = "https://discord.com/api/v10"


class DiscordConnectorError(ChannelError):
    """Structured error for Discord operations."""

    def __init__(self, message: str, error_code: str = "discord_error", details: dict[str, Any] | None = None):
        super().__init__(message, error_code, details)


class DiscordConnector(ChannelAdapter):
    """Discord HTTP API connector with shared security layers."""

    blocked_capabilities = CHANNEL_BLOCKED_CAPABILITIES | frozenset({
        "send_discord_message",
    })

    def __init__(
        self,
        bot_token: str = "",
        channel_id: str = "",
        guild_id: str = "",
        allowed_user_ids: list[str] | None = None,
    ):
        super().__init__(allowed_user_ids=allowed_user_ids)
        self._bot_token = bot_token
        self._channel_id = channel_id
        self._guild_id = guild_id
        self._bot_user_id: str | None = None

    def configure(self, **kwargs: Any) -> None:
        if "bot_token" in kwargs:
            self._bot_token = kwargs["bot_token"]
        if "channel_id" in kwargs:
            self._channel_id = kwargs["channel_id"]
        if "guild_id" in kwargs:
            self._guild_id = kwargs["guild_id"]
        if "allowed_user_ids" in kwargs:
            self._allowed_user_ids = [str(i) for i in (kwargs["allowed_user_ids"] or [])]

    def validate(self) -> dict[str, Any]:
        try:
            result = self._api_get("users/@me")
            self._bot_user_id = result.get("id")
            return {"valid": True, "bot_name": result.get("username"), "bot_user_id": self._bot_user_id}
        except DiscordConnectorError as exc:
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
            "guild_id": self._guild_id or None,
            "allowed_user_ids": self._allowed_user_ids,
        }

    def send_message(self, channel_id: str, text: str, **kwargs: Any) -> dict[str, Any]:
        target = channel_id or self._channel_id
        if not target:
            raise DiscordConnectorError("No channel_id provided and no default configured.", "no_channel")
        result = self._api_post(f"channels/{target}/messages", {"content": text[:2000]})
        return {
            "status": "success",
            "message_id": result.get("id"),
            "channel_id": target,
        }

    # ── Capability handler ──

    def send_discord_message(self, inputs: dict[str, Any]) -> dict[str, Any]:
        message = inputs.get("message", "")
        if not isinstance(message, str) or not message.strip():
            raise DiscordConnectorError("Field 'message' is required.", "invalid_input")
        channel = inputs.get("channel_id") or self._channel_id
        return self.send_message(channel, message)

    # ── Internal HTTP ──

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bot {self._bot_token}",
            "Content-Type": "application/json",
            "User-Agent": "CapabilityOS/1.0 (https://github.com/capability-os)",
        }

    def _api_get(self, endpoint: str) -> dict[str, Any]:
        if not self._bot_token:
            raise DiscordConnectorError("Bot token not configured.", "not_configured")
        url = f"{_DISCORD_API}/{endpoint}"
        req = Request(url, headers=self._headers())
        try:
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:300]
            except Exception:
                pass
            raise DiscordConnectorError(f"Discord API error: {detail or exc}", "api_error") from exc
        except URLError as exc:
            raise DiscordConnectorError(f"Connection failed: {exc.reason}", "connection_error") from exc

    def _api_post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._bot_token:
            raise DiscordConnectorError("Bot token not configured.", "not_configured")
        url = f"{_DISCORD_API}/{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, headers=self._headers(), method="POST")
        try:
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:300]
            except Exception:
                pass
            raise DiscordConnectorError(f"Discord API error: {detail or exc}", "api_error") from exc
        except URLError as exc:
            raise DiscordConnectorError(f"Connection failed: {exc.reason}", "connection_error") from exc


class DiscordPollingWorker(ChannelPollingWorker):
    """Polls Discord channel messages via HTTP API."""

    channel_name = "discord"
    poll_interval = 3.0

    def __init__(self, adapter: DiscordConnector, **kwargs: Any):
        super().__init__(adapter, **kwargs)
        self._discord: DiscordConnector = adapter
        self._last_message_id: str = ""

    def start(self) -> None:
        if not self._discord._bot_user_id:
            try:
                self._discord.validate()
            except Exception:
                pass
        super().start()

    def _fetch_updates(self) -> list[dict[str, Any]]:
        channel = self._discord._channel_id
        if not channel:
            return []
        try:
            endpoint = f"channels/{channel}/messages?limit=10"
            if self._last_message_id:
                endpoint += f"&after={self._last_message_id}"
            messages = self._discord._api_get(endpoint)
        except DiscordConnectorError:
            return []
        if not isinstance(messages, list):
            return []
        if messages:
            # Discord returns newest-first, reverse for chronological processing
            messages = list(reversed(messages))
            self._last_message_id = messages[-1].get("id", self._last_message_id)
        return messages

    def _extract_message(self, update: dict[str, Any]) -> tuple[str, str, str, str] | None:
        author = update.get("author", {})
        # Skip bots
        if author.get("bot"):
            return None
        user_id = author.get("id", "")
        if self._discord._bot_user_id and user_id == self._discord._bot_user_id:
            return None
        text = update.get("content", "").strip()
        if not text:
            return None
        channel = update.get("channel_id", self._discord._channel_id or "")
        display_name = author.get("username", "DiscordUser")
        return (channel, user_id, text, display_name)

    def _send_typing(self, channel_id: str) -> None:
        """Trigger typing indicator in Discord."""
        try:
            self._discord._api_post(f"channels/{channel_id}/typing", {})
        except DiscordConnectorError:
            pass
