"""Adapter that routes WhatsApp operations through the Baileys worker.

Falls back to the browser-based connector if Baileys is not available.
Keeps the same public API as WhatsAppWebConnector methods.
"""
from __future__ import annotations

import time
from typing import Any

from system.whatsapp_worker.whatsapp_client import WhatsAppClient, WhatsAppClientError


class BaileysAdapter:
    """Thin wrapper around WhatsAppClient that matches the connector method signatures."""

    def __init__(self) -> None:
        self._client = WhatsAppClient()
        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def ensure_connected(self, timeout_s: float = 30.0) -> dict[str, Any]:
        """Start the worker and wait for connection (or QR)."""
        if not self._client.alive:
            self._client.start()
            self._started = True

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            st = self._client.get_status()
            if st["connected"]:
                return {"status": "connected", "user": st.get("user")}
            if st.get("qr"):
                return {"status": "qr_required", "qr": st["qr"]}
            time.sleep(0.5)

        final = self._client.get_status()
        if final.get("status") == "error":
            return {"status": "blocked", "error": "Baileys connection blocked by WhatsApp (405). Use browser-based WhatsApp Web instead."}
        return {"status": "blocked", "error": f"Connection timeout after {timeout_s}s — no QR or connection received. Check Node.js and worker logs.", **final}

    @property
    def available(self) -> bool:
        """True if the worker can be started (worker.js + node exist)."""
        try:
            from pathlib import Path
            worker_js = Path(__file__).resolve().parent.parent.parent.parent / "whatsapp_worker" / "worker.js"
            node_modules = worker_js.parent / "node_modules" / "@whiskeysockets"
            return worker_js.exists() and node_modules.exists()
        except Exception:
            return False

    @property
    def connected(self) -> bool:
        return self._client.get_status().get("connected", False)

    # ------------------------------------------------------------------
    # Operations (match WhatsAppWebConnector method signatures)
    # ------------------------------------------------------------------

    def send_whatsapp_message(self, inputs: dict[str, Any]) -> dict[str, Any]:
        self._require_connected()
        chat_name = (
            inputs.get("chat_name")
            or inputs.get("phone_number")
            or inputs.get("contact")
            or inputs.get("recipient")
            or ""
        )
        message = inputs.get("message", "")
        if not chat_name:
            raise WhatsAppClientError("invalid_input", "Field 'chat_name' is required.")
        if not message:
            raise WhatsAppClientError("invalid_input", "Field 'message' is required.")

        result = self._client.send_message(chat_name, message, timeout_s=30.0)
        return {
            "status": "success",
            "session_id": "baileys",
            "message": message,
            "confirmation": result.get("confirmation", "sent"),
            "jid": result.get("jid"),
        }

    def search_whatsapp_chat(self, inputs: dict[str, Any]) -> dict[str, Any]:
        self._require_connected()
        query = inputs.get("chat_name") or inputs.get("query") or ""
        if not query:
            raise WhatsAppClientError("invalid_input", "Field 'chat_name' is required.")

        result = self._client.search_contact(query, timeout_s=10.0)
        contacts = result.get("contacts", [])
        return {
            "status": "success" if contacts else "not_found",
            "session_id": "baileys",
            "chat_name": query,
            "selected": len(contacts) == 1,
            "matches": [c.get("jid", "") for c in contacts],
        }

    def get_status(self) -> dict[str, Any]:
        return self._client.get_status()

    def get_qr(self) -> str | None:
        return self._client.get_qr()

    def close_session(self) -> dict[str, Any]:
        self._client.stop()
        return {"status": "closed"}

    def logout(self) -> dict[str, Any]:
        try:
            return self._client.logout()
        except WhatsAppClientError:
            return {"status": "closed"}
        finally:
            self._client.stop()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_connected(self) -> None:
        if not self.connected:
            status = self.ensure_connected(timeout_s=15.0)
            if status.get("qr"):
                raise WhatsAppClientError(
                    "wsp_qr_required",
                    "WhatsApp requires QR authentication. Check Control Center > Integrations for the QR code.",
                )
            if not self.connected:
                raise WhatsAppClientError(
                    "wsp_not_connected",
                    "WhatsApp is not connected. Start the worker from Control Center > Integrations.",
                )
