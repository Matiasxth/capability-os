"""Integration route handlers: telegram, whatsapp, generic integrations."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any


def _resp(code, data):
    from system.core.ui_bridge.api_server import APIResponse
    return APIResponse(code, data)


def _err(code, ec, msg):
    from system.core.ui_bridge.api_server import APIRequestError
    raise APIRequestError(code, ec, msg)


# --- Generic integrations ---

def list_integrations(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, {"integrations": service._list_integrations()})


def inspect_integration(service: Any, payload: Any, integration_id: str = "", **kw: Any):
    return _resp(HTTPStatus.OK, {"integration": service._inspect_integration(integration_id)})


def validate_integration(service: Any, payload: Any, integration_id: str = "", **kw: Any):
    return _resp(HTTPStatus.OK, service._validate_integration(integration_id))


def enable_integration(service: Any, payload: Any, integration_id: str = "", **kw: Any):
    result = service._enable_integration(integration_id)
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("integration_changed", {"action": "enabled", "integration_id": integration_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, result)


def disable_integration(service: Any, payload: Any, integration_id: str = "", **kw: Any):
    result = service._disable_integration(integration_id)
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("integration_changed", {"action": "disabled", "integration_id": integration_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, result)


# --- WhatsApp ---

def whatsapp_selectors_override(service: Any, payload: Any, **kw: Any):
    body = payload or {}
    overrides = body.get("overrides", {})
    if isinstance(overrides, dict):
        service.phase10_whatsapp_executor.connector.apply_selector_overrides(overrides)
        try:
            current = service.settings_service.load_settings()
            current.setdefault("whatsapp", {})["selector_overrides"] = overrides
            service.settings_service.save_settings(current)
        except Exception:
            pass
    return _resp(HTTPStatus.OK, {"status": "success"})


def whatsapp_selectors_health(service: Any, payload: Any, **kw: Any):
    report = service.phase10_whatsapp_executor.connector.probe_selectors()
    return _resp(HTTPStatus.OK, {"selectors": report})


def whatsapp_close_session(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, service.phase10_whatsapp_executor.connector.close_whatsapp_session())


def whatsapp_session_status(service: Any, payload: Any, **kw: Any):
    if hasattr(service, "whatsapp_manager"):
        st = service.whatsapp_manager.get_status()
        return _resp(HTTPStatus.OK, {"active": st.get("connected", False), **st})
    status = service.phase10_whatsapp_executor.connector.get_session_status()
    return _resp(HTTPStatus.OK, status)


def whatsapp_start(service: Any, payload: Any, **kw: Any):
    if hasattr(service, "whatsapp_manager"):
        return _resp(HTTPStatus.OK, service.whatsapp_manager.start())
    return _resp(HTTPStatus.OK, service._start_whatsapp_worker())


def whatsapp_stop(service: Any, payload: Any, **kw: Any):
    if hasattr(service, "whatsapp_manager"):
        return _resp(HTTPStatus.OK, service.whatsapp_manager.stop())
    return _resp(HTTPStatus.OK, {"status": "not_available"})


def whatsapp_qr(service: Any, payload: Any, **kw: Any):
    if hasattr(service, "whatsapp_manager"):
        st = service.whatsapp_manager.get_status()
        return _resp(HTTPStatus.OK, {"qr": st.get("qr"), "qr_image": st.get("qr_image")})
    status = service.phase10_whatsapp_executor.connector.get_session_status()
    qr_data = status.get("qr")
    result: dict[str, Any] = {"qr": qr_data}
    if qr_data:
        result["qr_image"] = service._qr_to_data_url(qr_data)
    return _resp(HTTPStatus.OK, result)


def whatsapp_configure(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "whatsapp_manager"):
        return _resp(HTTPStatus.BAD_REQUEST, {"status": "error", "error": "Backend manager not available"})

    backend = payload.get("backend")
    official_config = payload.get("official", {})
    allowed_user_ids = payload.get("allowed_user_ids", [])

    # Save to settings
    current = service.settings_service.load_settings()
    wsp = current.get("whatsapp", {})
    if not isinstance(wsp, dict):
        wsp = {}
    if backend:
        wsp["backend"] = backend
    if official_config:
        wsp["official"] = official_config
    if allowed_user_ids is not None:
        wsp["allowed_user_ids"] = allowed_user_ids
    current["whatsapp"] = wsp
    service.settings_service.save_settings(current)

    # Apply backend switch
    if backend:
        service.whatsapp_manager.switch(backend)

    # Apply official config
    official_backend = service.whatsapp_manager._backends.get("official")
    if official_backend and official_config:
        official_backend.configure(official_config)

    from system.core.ui_bridge.event_bus import event_bus
    event_bus.emit("integration_changed", {"action": "whatsapp_configured", "backend": backend})
    return _resp(HTTPStatus.OK, {"status": "ok", "active_backend": service.whatsapp_manager.active_id})


def whatsapp_switch_backend(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "whatsapp_manager"):
        return _resp(HTTPStatus.BAD_REQUEST, {"status": "error", "error": "Backend manager not available"})
    backend = payload.get("backend", "")
    result = service.whatsapp_manager.switch(backend)
    if result.get("status") == "ok":
        # Persist
        current = service.settings_service.load_settings()
        wsp = current.get("whatsapp", {})
        if not isinstance(wsp, dict):
            wsp = {}
        wsp["backend"] = backend
        current["whatsapp"] = wsp
        service.settings_service.save_settings(current)
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("integration_changed", {"action": "whatsapp_backend_switched", "backend": backend})
    return _resp(HTTPStatus.OK, result)


def whatsapp_list_backends(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "whatsapp_manager"):
        return _resp(HTTPStatus.OK, {"backends": []})
    return _resp(HTTPStatus.OK, {"backends": service.whatsapp_manager.list_backends()})


def whatsapp_debug(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "whatsapp_manager") or not service.whatsapp_manager.active:
        return _resp(HTTPStatus.OK, {"status": "no_backend"})
    backend = service.whatsapp_manager.active
    if hasattr(backend, "debug_screenshot"):
        return _resp(HTTPStatus.OK, backend.debug_screenshot())
    return _resp(HTTPStatus.OK, {"status": "not_supported"})


def whatsapp_debug_chats(service: Any, payload: Any, **kw: Any):
    if not hasattr(service, "whatsapp_manager") or not service.whatsapp_manager.active:
        return _resp(HTTPStatus.OK, {"status": "no_backend"})
    backend = service.whatsapp_manager.active
    if hasattr(backend, "debug_chats"):
        return _resp(HTTPStatus.OK, backend.debug_chats())
    return _resp(HTTPStatus.OK, {"status": "not_supported"})


def whatsapp_reply_status(service: Any, payload: Any, **kw: Any):
    if hasattr(service, "whatsapp_reply_worker"):
        return _resp(HTTPStatus.OK, service.whatsapp_reply_worker.get_status())
    return _resp(HTTPStatus.OK, {"running": False})


# --- Telegram ---

def telegram_status(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, service.telegram_connector.get_status())


def telegram_configure(service: Any, payload: Any, **kw: Any):
    body = payload or {}
    token = body.get("bot_token", "")
    chat_id = body.get("default_chat_id", "")
    user_ids = body.get("allowed_user_ids", [])
    usernames = body.get("allowed_usernames", [])
    service.telegram_connector.configure(token, chat_id, user_ids, usernames)
    display_name = body.get("display_name", "")
    if not display_name:
        try:
            display_name = service.user_context.get_context().get("custom_preferences", {}).get("name", "")
        except Exception:
            pass
    if display_name:
        names = {str(uid): display_name for uid in user_ids}
        service.telegram_connector.set_user_display_names(names)
    try:
        current = service.settings_service.load_settings()
        tg_current = current.get("telegram", {})
        tg_current["bot_token"] = token
        tg_current["default_chat_id"] = chat_id
        if display_name:
            tg_current["display_name"] = display_name
        tg_current["allowed_user_ids"] = user_ids
        tg_current["allowed_usernames"] = usernames
        current["telegram"] = tg_current
        service.settings_service.save_settings(current)
    except Exception:
        pass
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("integration_changed", {"action": "telegram_configured"})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, service.telegram_connector.get_status())


def telegram_test(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, service.telegram_connector.validate())


def telegram_polling_start(service: Any, payload: Any, **kw: Any):
    service.telegram_polling_worker.start()
    try:
        current = service.settings_service.load_settings()
        current.setdefault("telegram", {})["polling_enabled"] = True
        service.settings_service.save_settings(current)
    except Exception:
        pass
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("integration_changed", {"action": "telegram_polling_started"})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, {"status": "started", **service.telegram_polling_worker.get_status()})


def telegram_polling_stop(service: Any, payload: Any, **kw: Any):
    service.telegram_polling_worker.stop()
    try:
        current = service.settings_service.load_settings()
        current.setdefault("telegram", {})["polling_enabled"] = False
        service.settings_service.save_settings(current)
    except Exception:
        pass
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("integration_changed", {"action": "telegram_polling_stopped"})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, {"status": "stopped"})


def telegram_polling_status(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, service.telegram_polling_worker.get_status())


# --- Slack ---

def slack_status(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, service.slack_connector.get_status())


def slack_configure(service: Any, payload: Any, **kw: Any):
    body = payload or {}
    service.slack_connector.configure(
        bot_token=body.get("bot_token", ""),
        channel_id=body.get("channel_id", ""),
        allowed_user_ids=body.get("allowed_user_ids", []),
    )
    try:
        current = service.settings_service.load_settings()
        current["slack"] = {
            "bot_token": body.get("bot_token", ""),
            "channel_id": body.get("channel_id", ""),
            "allowed_user_ids": body.get("allowed_user_ids", []),
        }
        service.settings_service.save_settings(current)
    except Exception:
        pass
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("integration_changed", {"action": "slack_configured"})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, service.slack_connector.get_status())


def slack_test(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, service.slack_connector.validate())


def slack_polling_start(service: Any, payload: Any, **kw: Any):
    service.slack_polling_worker.start()
    try:
        current = service.settings_service.load_settings()
        current.setdefault("slack", {})["polling_enabled"] = True
        service.settings_service.save_settings(current)
    except Exception:
        pass
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("integration_changed", {"action": "slack_polling_started"})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, {"status": "started", **service.slack_polling_worker.get_status()})


def slack_polling_stop(service: Any, payload: Any, **kw: Any):
    service.slack_polling_worker.stop()
    try:
        current = service.settings_service.load_settings()
        current.setdefault("slack", {})["polling_enabled"] = False
        service.settings_service.save_settings(current)
    except Exception:
        pass
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("integration_changed", {"action": "slack_polling_stopped"})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, {"status": "stopped"})


def slack_polling_status(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, service.slack_polling_worker.get_status())


# --- Discord ---

def discord_status(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, service.discord_connector.get_status())


def discord_configure(service: Any, payload: Any, **kw: Any):
    body = payload or {}
    service.discord_connector.configure(
        bot_token=body.get("bot_token", ""),
        channel_id=body.get("channel_id", ""),
        guild_id=body.get("guild_id", ""),
        allowed_user_ids=body.get("allowed_user_ids", []),
    )
    try:
        current = service.settings_service.load_settings()
        current["discord"] = {
            "bot_token": body.get("bot_token", ""),
            "channel_id": body.get("channel_id", ""),
            "guild_id": body.get("guild_id", ""),
            "allowed_user_ids": body.get("allowed_user_ids", []),
        }
        service.settings_service.save_settings(current)
    except Exception:
        pass
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("integration_changed", {"action": "discord_configured"})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, service.discord_connector.get_status())


def discord_test(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, service.discord_connector.validate())


def discord_polling_start(service: Any, payload: Any, **kw: Any):
    service.discord_polling_worker.start()
    try:
        current = service.settings_service.load_settings()
        current.setdefault("discord", {})["polling_enabled"] = True
        service.settings_service.save_settings(current)
    except Exception:
        pass
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("integration_changed", {"action": "discord_polling_started"})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, {"status": "started", **service.discord_polling_worker.get_status()})


def discord_polling_stop(service: Any, payload: Any, **kw: Any):
    service.discord_polling_worker.stop()
    try:
        current = service.settings_service.load_settings()
        current.setdefault("discord", {})["polling_enabled"] = False
        service.settings_service.save_settings(current)
    except Exception:
        pass
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("integration_changed", {"action": "discord_polling_stopped"})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, {"status": "stopped"})


def discord_polling_status(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, service.discord_polling_worker.get_status())
