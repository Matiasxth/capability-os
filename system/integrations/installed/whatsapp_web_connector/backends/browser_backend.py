"""Browser backend — Node.js Puppeteer subprocess via IPC.

Uses the same WhatsAppClient IPC pattern as Baileys but points
at ``browser_worker.js`` instead of ``worker.js``.

Incoming messages are emitted to event_bus by WhatsAppClient._read_loop()
(same path as Baileys).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .base import WhatsAppBackend


_WORKER_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "whatsapp_worker"


class BrowserBackend(WhatsAppBackend):
    backend_id = "browser"

    def __init__(self) -> None:
        self._client: Any = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from system.whatsapp_worker.whatsapp_client import WhatsAppClient
            self._client = WhatsAppClient(worker_script="browser_worker.js")
            return self._client
        except Exception:
            return None

    def start(self, timeout_s: float = 30.0) -> dict[str, Any]:
        client = self._ensure_client()
        if client is None:
            return {"status": "error", "error": "Browser worker client unavailable", "connected": False, "backend": self.backend_id}

        if not client.alive:
            try:
                client.start()
            except Exception as exc:
                return {"status": "error", "error": str(exc), "connected": False, "backend": self.backend_id}

        # Wait for connected or QR
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            st = client.get_status()
            # Worker crashed
            if st.get("status") == "error":
                return {"status": "error", "error": "Browser worker failed. Check Node.js/Puppeteer installation.", "connected": False, "backend": self.backend_id}
            if not client.alive:
                return {"status": "error", "error": "Browser worker process died unexpectedly.", "connected": False, "backend": self.backend_id}
            if st.get("connected"):
                return {"status": "connected", "connected": True, "user": st.get("user"), "backend": self.backend_id}
            if st.get("qr"):
                qr_val = st["qr"]
                result: dict[str, Any] = {"status": "qr_ready", "connected": False, "backend": self.backend_id}
                # qr_image is already a data URL from browser_worker.js
                if qr_val.startswith("data:"):
                    result["qr_image"] = qr_val
                else:
                    result["qr"] = qr_val
                    # Try to convert to image
                    try:
                        import base64, io, qrcode  # type: ignore
                        img = qrcode.make(qr_val)
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        result["qr_image"] = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"
                    except ImportError:
                        pass
                return result
            time.sleep(0.5)

        return {"status": "timeout", "error": f"No QR or connection in {timeout_s}s", "connected": False, "backend": self.backend_id}

    def stop(self) -> dict[str, Any]:
        if self._client:
            self._client.stop()
        return {"status": "closed"}

    def get_status(self) -> dict[str, Any]:
        if self._client is None or not self._client.alive:
            return {"connected": False, "status": "disconnected", "backend": self.backend_id}
        st = self._client.get_status()
        result: dict[str, Any] = {
            "connected": st.get("connected", False),
            "status": st.get("status", "disconnected"),
            "backend": self.backend_id,
        }
        if st.get("qr"):
            qr_val = st["qr"]
            if qr_val.startswith("data:"):
                result["qr_image"] = qr_val
        return result

    def debug_chats(self) -> dict[str, Any]:
        """Read chat previews from the browser for debugging."""
        if self._client is None or not self._client.alive:
            return {"status": "error", "error": "Not connected"}
        from system.whatsapp_worker.whatsapp_client import WhatsAppClientError
        try:
            result = self._client._send_command("debug_chats", {}, 10.0)
            return result
        except WhatsAppClientError as exc:
            return {"status": "error", "error": str(exc)}

    def debug_screenshot(self) -> dict[str, Any]:
        """Take screenshot via IPC for debugging."""
        if self._client is None or not self._client.alive:
            return {"status": "error", "error": "Not connected"}
        from system.whatsapp_worker.whatsapp_client import WhatsAppClientError
        try:
            result = self._client._send_command("screenshot", {}, 10.0)
            return {"status": "ok", "image": result.get("image")}
        except WhatsAppClientError as exc:
            return {"status": "error", "error": str(exc)}

    def send_message(self, to: str, message: str, timeout_s: float = 30.0) -> dict[str, Any]:
        if self._client is None or not self._client.alive:
            return {"status": "error", "error": "Browser not connected"}
        from system.whatsapp_worker.whatsapp_client import WhatsAppClientError
        try:
            result = self._client._send_command("send_message", {"to": to, "message": message}, timeout_s)
            return {"status": "success", "message": message, "confirmation": result.get("confirmation", "sent"), "backend": self.backend_id}
        except WhatsAppClientError as exc:
            return {"status": "error", "error": str(exc)}

    def search_contact(self, query: str, timeout_s: float = 10.0) -> dict[str, Any]:
        if self._client is None or not self._client.alive:
            return {"status": "error", "error": "Browser not connected"}
        from system.whatsapp_worker.whatsapp_client import WhatsAppClientError
        try:
            result = self._client._send_command("search_contact", {"query": query}, timeout_s)
            return {"status": "success", "contacts": result.get("contacts", []), "backend": self.backend_id}
        except WhatsAppClientError as exc:
            return {"status": "error", "error": str(exc)}

    def configure(self, config: dict[str, Any]) -> None:
        pass  # Browser uses QR auth, no config needed

    @property
    def available(self) -> bool:
        worker_js = _WORKER_DIR / "browser_worker.js"
        node_modules = _WORKER_DIR / "node_modules" / "puppeteer"
        return worker_js.exists() and node_modules.exists()

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.alive and self._client.get_status().get("connected", False)
