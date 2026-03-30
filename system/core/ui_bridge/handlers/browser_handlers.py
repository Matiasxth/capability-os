"""Browser-related route handlers: CDP, Chrome, restart."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any


def restart_worker(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse
    result = service._restart_browser_worker()
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("browser_changed", {"action": "worker_restarted"})
    except Exception:
        pass
    return APIResponse(HTTPStatus.OK, result)


def cdp_status(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse
    return APIResponse(HTTPStatus.OK, service._cdp_status())


def launch_chrome(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse
    result = service._launch_chrome()
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("browser_changed", {"action": "chrome_launched"})
    except Exception:
        pass
    return APIResponse(HTTPStatus.OK, result)


def open_whatsapp(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse
    return APIResponse(HTTPStatus.OK, service._open_whatsapp())


def connect_cdp(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse
    result = service._connect_worker_to_cdp()
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("browser_changed", {"action": "cdp_connected"})
    except Exception:
        pass
    return APIResponse(HTTPStatus.OK, result)
