"""WhatsApp Backend Manager — switches between Official API, Browser, and Baileys."""
from __future__ import annotations

from typing import Any

from .base import WhatsAppBackend


VALID_BACKENDS = ("official", "browser", "baileys")


class WhatsAppBackendManager:
    """Holds references to all backends and delegates to the active one."""

    def __init__(self) -> None:
        self._backends: dict[str, WhatsAppBackend] = {}
        self._active_id: str = "browser"
        self._active: WhatsAppBackend | None = None

    def register(self, backend: WhatsAppBackend) -> None:
        self._backends[backend.backend_id] = backend

    def switch(self, backend_id: str) -> dict[str, Any]:
        """Stop current backend (if different) and activate the new one."""
        if backend_id not in VALID_BACKENDS:
            return {"status": "error", "error": f"Invalid backend: {backend_id}"}

        target = self._backends.get(backend_id)
        if target is None:
            return {"status": "error", "error": f"Backend '{backend_id}' not registered"}

        if self._active and self._active.backend_id != backend_id:
            try:
                self._active.stop()
            except Exception:
                pass

        self._active_id = backend_id
        self._active = target
        return {"status": "ok", "active_backend": backend_id}

    @property
    def active(self) -> WhatsAppBackend | None:
        return self._active

    @property
    def active_id(self) -> str:
        return self._active_id

    def get_status(self) -> dict[str, Any]:
        if self._active is None:
            return {"connected": False, "status": "no_backend", "backend": self._active_id}
        status = self._active.get_status()
        status["backend"] = self._active_id
        return status

    def start(self, timeout_s: float = 30.0) -> dict[str, Any]:
        if self._active is None:
            return {"status": "error", "error": "No backend selected", "connected": False}
        result = self._active.start(timeout_s=timeout_s)
        result.setdefault("backend", self._active_id)
        return result

    def stop(self) -> dict[str, Any]:
        if self._active is None:
            return {"status": "idle"}
        return self._active.stop()

    def send_message(self, to: str, message: str, timeout_s: float = 30.0) -> dict[str, Any]:
        if self._active is None or not self._active.connected:
            return {"status": "error", "error": "WhatsApp not connected"}
        return self._active.send_message(to, message, timeout_s=timeout_s)

    def search_contact(self, query: str, timeout_s: float = 10.0) -> dict[str, Any]:
        if self._active is None or not self._active.connected:
            return {"status": "error", "error": "WhatsApp not connected"}
        return self._active.search_contact(query, timeout_s=timeout_s)

    def list_backends(self) -> list[dict[str, Any]]:
        result = []
        for bid in VALID_BACKENDS:
            b = self._backends.get(bid)
            result.append({
                "id": bid,
                "registered": b is not None,
                "available": b.available if b else False,
                "active": bid == self._active_id,
            })
        return result
