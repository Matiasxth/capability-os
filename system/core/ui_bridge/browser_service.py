"""Browser service — moved from api_server.py god-object.

Browser-related operations called by browser_handlers.py.
"""
from __future__ import annotations

from typing import Any


def restart_browser_worker(service: Any) -> dict[str, Any]:
    return service._restart_browser_worker()

def cdp_status(service: Any) -> dict[str, Any]:
    return service._cdp_status()

def launch_chrome(service: Any) -> dict[str, Any]:
    return service._launch_chrome()

def open_whatsapp(service: Any) -> dict[str, Any]:
    return service._open_whatsapp()

def connect_worker_to_cdp(service: Any) -> dict[str, Any]:
    return service._connect_worker_to_cdp()

def find_chrome() -> str | None:
    """Find Chrome executable on the system."""
    # This will be moved fully in a later phase
    from system.core.ui_bridge.api_server import CapabilityOSUIBridgeService
    return CapabilityOSUIBridgeService._find_chrome()
