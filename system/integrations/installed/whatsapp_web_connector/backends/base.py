"""Abstract base class for WhatsApp backends.

All backends (Official API, Browser/Puppeteer, Baileys) implement this
interface so the connector can switch between them transparently.

Incoming messages MUST be emitted to the event_bus as::

    event_bus.emit("whatsapp_message", {
        "from": "5691234567@s.whatsapp.net",
        "pushName": "John",
        "text": "Hello",
        "messageId": "msg_abc123",
    })
"""
from __future__ import annotations

import abc
from typing import Any


class WhatsAppBackend(abc.ABC):
    """Uniform interface every WhatsApp backend must implement."""

    backend_id: str = ""  # "official", "browser", "baileys"

    @abc.abstractmethod
    def start(self, timeout_s: float = 30.0) -> dict[str, Any]:
        """Connect / start the backend.

        Returns dict with at least:
          - status: "connected" | "qr_ready" | "error" | ...
          - connected: bool
          - backend: str
        Optionally:
          - qr_image: str (data:image/png;base64,...)
          - user: dict
          - error: str
        """

    @abc.abstractmethod
    def stop(self) -> dict[str, Any]:
        """Disconnect / stop the backend. Returns {status: "closed"}."""

    @abc.abstractmethod
    def get_status(self) -> dict[str, Any]:
        """Current connection status.

        Returns dict with at least:
          - connected: bool
          - status: str
          - backend: str
        """

    @abc.abstractmethod
    def send_message(self, to: str, message: str, timeout_s: float = 30.0) -> dict[str, Any]:
        """Send a text message.

        Returns dict with at least:
          - status: "success" | "error"
        """

    @abc.abstractmethod
    def search_contact(self, query: str, timeout_s: float = 10.0) -> dict[str, Any]:
        """Search for a contact by name or phone.

        Returns dict with at least:
          - status: "success" | "not_found" | "not_supported"
          - contacts: list (may be empty)
        """

    @abc.abstractmethod
    def configure(self, config: dict[str, Any]) -> None:
        """Apply runtime configuration (tokens, IDs, etc.)."""

    @property
    @abc.abstractmethod
    def available(self) -> bool:
        """True if the backend can potentially be started (deps installed, etc.)."""

    @property
    @abc.abstractmethod
    def connected(self) -> bool:
        """True if currently connected and ready to send/receive."""
