"""Official API backend — WhatsApp Business Cloud API via Meta.

Sends messages via HTTP POST to Meta's Graph API.
Receives messages via a webhook HTTP server running on a background thread.

Requires:
  - access_token: Meta app access token
  - phone_number_id: WhatsApp phone number ID
  - verify_token: webhook verification token (you choose this)

For local development, expose the webhook via ngrok:
  ngrok http 5001
Then configure the webhook URL in Meta App Dashboard.
"""
from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from .base import WhatsAppBackend

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
DEFAULT_WEBHOOK_PORT = 5001


class OfficialBackend(WhatsAppBackend):
    backend_id = "official"

    def __init__(self) -> None:
        self._access_token: str = ""
        self._phone_number_id: str = ""
        self._verify_token: str = ""
        self._webhook_port: int = DEFAULT_WEBHOOK_PORT
        self._webhook_server: HTTPServer | None = None
        self._webhook_thread: threading.Thread | None = None
        self._running = False

    # ------------------------------------------------------------------
    # WhatsAppBackend interface
    # ------------------------------------------------------------------

    def start(self, timeout_s: float = 30.0) -> dict[str, Any]:
        if not self._access_token or not self._phone_number_id:
            return {
                "status": "error",
                "error": "Configure access_token and phone_number_id first",
                "connected": False,
                "backend": self.backend_id,
            }

        # Start webhook server
        if not self._running:
            try:
                self._start_webhook()
            except Exception as exc:
                return {"status": "error", "error": f"Webhook start failed: {exc}", "connected": False, "backend": self.backend_id}

        return {"status": "connected", "connected": True, "backend": self.backend_id}

    def stop(self) -> dict[str, Any]:
        self._stop_webhook()
        return {"status": "closed"}

    def get_status(self) -> dict[str, Any]:
        return {
            "connected": self._running,
            "status": "connected" if self._running else "disconnected",
            "backend": self.backend_id,
            "phone_number_id": self._phone_number_id,
            "webhook_port": self._webhook_port,
            "webhook_url": f"http://localhost:{self._webhook_port}/webhook",
        }

    def send_message(self, to: str, message: str, timeout_s: float = 30.0) -> dict[str, Any]:
        if not self._access_token or not self._phone_number_id:
            return {"status": "error", "error": "Not configured"}

        # Normalize phone number (remove +, spaces, dashes)
        phone = to.replace("+", "").replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        # Remove @s.whatsapp.net suffix if present
        phone = phone.split("@")[0]

        url = f"{GRAPH_API_BASE}/{self._phone_number_id}/messages"
        payload = json.dumps({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": "text",
            "text": {"body": message},
        }).encode()

        req = Request(url, data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {self._access_token}")
        req.add_header("Content-Type", "application/json")

        try:
            with urlopen(req, timeout=timeout_s) as resp:
                data = json.loads(resp.read().decode())
                msg_id = ""
                messages = data.get("messages", [])
                if messages:
                    msg_id = messages[0].get("id", "")
                return {"status": "success", "message_id": msg_id, "to": phone, "confirmation": "sent", "backend": self.backend_id}
        except HTTPError as exc:
            body = exc.read().decode() if exc.readable() else ""
            return {"status": "error", "error": f"API error {exc.code}: {body[:300]}"}
        except URLError as exc:
            return {"status": "error", "error": f"Network error: {exc.reason}"}

    def search_contact(self, query: str, timeout_s: float = 10.0) -> dict[str, Any]:
        return {"status": "not_supported", "contacts": [], "error": "Contact search not available with Official API. Use phone numbers directly.", "backend": self.backend_id}

    def configure(self, config: dict[str, Any]) -> None:
        self._access_token = str(config.get("access_token", self._access_token)).strip()
        self._phone_number_id = str(config.get("phone_number_id", self._phone_number_id)).strip()
        self._verify_token = str(config.get("verify_token", self._verify_token)).strip()
        port = config.get("webhook_port", self._webhook_port)
        if isinstance(port, int) and port > 0:
            self._webhook_port = port

    @property
    def available(self) -> bool:
        return bool(self._access_token and self._phone_number_id)

    @property
    def connected(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Webhook server
    # ------------------------------------------------------------------

    def _start_webhook(self) -> None:
        backend = self

        class WebhookHandler(BaseHTTPRequestHandler):
            server_version = "CapOS-WhatsApp-Webhook/1.0"

            def log_message(self, *_a) -> None:
                pass

            def do_GET(self) -> None:
                """Meta webhook verification."""
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                mode = params.get("hub.mode", [""])[0]
                token = params.get("hub.verify_token", [""])[0]
                challenge = params.get("hub.challenge", [""])[0]

                if mode == "subscribe" and token == backend._verify_token:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(challenge.encode())
                else:
                    self.send_response(403)
                    self.end_headers()

            def do_POST(self) -> None:
                """Incoming message webhook."""
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    self.send_response(200)
                    self.end_headers()
                    return

                raw = self.rfile.read(length).decode()
                self.send_response(200)
                self.end_headers()

                try:
                    data = json.loads(raw)
                    backend._process_webhook(data)
                except Exception:
                    pass

        self._webhook_server = HTTPServer(("0.0.0.0", self._webhook_port), WebhookHandler)
        self._running = True
        self._webhook_thread = threading.Thread(target=self._webhook_server.serve_forever, daemon=True)
        self._webhook_thread.start()
        print(f"  WhatsApp Official webhook: http://0.0.0.0:{self._webhook_port}/webhook")

    def _stop_webhook(self) -> None:
        self._running = False
        if self._webhook_server:
            self._webhook_server.shutdown()
            self._webhook_server = None

    def _process_webhook(self, data: dict[str, Any]) -> None:
        """Parse Meta Cloud API webhook payload and emit to event_bus."""
        try:
            from system.core.ui_bridge.event_bus import event_bus
        except ImportError:
            return

        entries = data.get("entry", [])
        for entry in entries:
            changes = entry.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                messages = value.get("messages", [])
                contacts = value.get("contacts", [])

                contact_map = {}
                for c in contacts:
                    wa_id = c.get("wa_id", "")
                    name = c.get("profile", {}).get("name", "")
                    if wa_id:
                        contact_map[wa_id] = name

                for msg in messages:
                    if msg.get("type") != "text":
                        continue
                    from_id = msg.get("from", "")
                    text = msg.get("text", {}).get("body", "")
                    msg_id = msg.get("id", "")
                    push_name = contact_map.get(from_id, from_id)

                    if text:
                        event_bus.emit("whatsapp_message", {
                            "from": f"{from_id}@s.whatsapp.net",
                            "pushName": push_name,
                            "text": text[:200],
                            "messageId": msg_id,
                        })
