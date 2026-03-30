"""Baileys backend — wraps the existing BaileysAdapter / WhatsAppClient.

Incoming messages are already emitted to event_bus by WhatsAppClient._read_loop().
"""
from __future__ import annotations

from typing import Any

from .base import WhatsAppBackend


class BaileysBackend(WhatsAppBackend):
    backend_id = "baileys"

    def __init__(self) -> None:
        self._adapter: Any = None

    def _ensure_adapter(self) -> Any:
        if self._adapter is not None:
            return self._adapter
        try:
            from system.integrations.installed.whatsapp_web_connector.baileys_adapter import BaileysAdapter
            adapter = BaileysAdapter()
            if adapter.available:
                self._adapter = adapter
                return adapter
        except Exception:
            pass
        return None

    def start(self, timeout_s: float = 30.0) -> dict[str, Any]:
        adapter = self._ensure_adapter()
        if adapter is None:
            return {"status": "error", "error": "Baileys not available. Run: cd system/whatsapp_worker && npm install", "connected": False, "backend": self.backend_id}
        result = adapter.ensure_connected(timeout_s=timeout_s)
        status = result.get("status", "unknown")
        response: dict[str, Any] = {"status": status, "connected": status == "connected", "backend": self.backend_id}
        if result.get("qr"):
            response["qr"] = result["qr"]
            # Convert QR string to image
            try:
                import base64, io, qrcode  # type: ignore
                img = qrcode.make(result["qr"])
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                response["qr_image"] = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"
            except ImportError:
                pass
        if result.get("user"):
            response["user"] = result["user"]
        if result.get("error"):
            response["error"] = result["error"]
        return response

    def stop(self) -> dict[str, Any]:
        if self._adapter:
            try:
                return self._adapter.close_session()
            except Exception:
                pass
        return {"status": "closed"}

    def get_status(self) -> dict[str, Any]:
        if self._adapter is None:
            return {"connected": False, "status": "not_available", "backend": self.backend_id}
        st = self._adapter.get_status()
        return {
            "connected": st.get("connected", False),
            "status": st.get("status", "disconnected"),
            "user": st.get("user"),
            "qr": st.get("qr"),
            "backend": self.backend_id,
        }

    def send_message(self, to: str, message: str, timeout_s: float = 30.0) -> dict[str, Any]:
        if self._adapter is None or not self._adapter.connected:
            return {"status": "error", "error": "Baileys not connected"}
        return self._adapter.send_whatsapp_message({"chat_name": to, "message": message})

    def search_contact(self, query: str, timeout_s: float = 10.0) -> dict[str, Any]:
        if self._adapter is None or not self._adapter.connected:
            return {"status": "error", "error": "Baileys not connected"}
        return self._adapter.search_whatsapp_chat({"chat_name": query})

    def configure(self, config: dict[str, Any]) -> None:
        pass  # Baileys uses QR auth, no config needed

    @property
    def available(self) -> bool:
        return self._ensure_adapter() is not None

    @property
    def connected(self) -> bool:
        return self._adapter is not None and self._adapter.connected
