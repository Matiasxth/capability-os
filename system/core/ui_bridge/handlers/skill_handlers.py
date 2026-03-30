"""Skill route handlers: list, install, uninstall, get."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any


def _resp(code, data):
    from system.core.ui_bridge.api_server import APIResponse
    return APIResponse(code, data)


def _err(code, ec, msg):
    from system.core.ui_bridge.api_server import APIRequestError
    raise APIRequestError(code, ec, msg)


def list_skills(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, {"skills": service.skill_registry.list_installed()})


def get_skill(service: Any, payload: Any, skill_id: str = "", **kw: Any):
    skill = service.skill_registry.get_skill(skill_id)
    if skill is None:
        _err(HTTPStatus.NOT_FOUND, "skill_not_found", f"Skill '{skill_id}' not found.")
    return _resp(HTTPStatus.OK, {"skill": skill})


def install_skill(service: Any, payload: Any, **kw: Any):
    body = payload or {}
    source = body.get("source", "")
    if not source:
        _err(HTTPStatus.BAD_REQUEST, "missing_source", "Field 'source' (path) is required.")
    try:
        from system.core.skills.skill_manifest import SkillManifestError
        manifest = service.skill_registry.install_from_path(source)
        try:
            from system.core.ui_bridge.event_bus import event_bus
            event_bus.emit("integration_changed", {"action": "skill_installed", "skill_id": manifest.get("id", "")})
        except Exception:
            pass
        return _resp(HTTPStatus.OK, {"status": "success", "skill": manifest})
    except SkillManifestError as exc:
        _err(HTTPStatus.BAD_REQUEST, "skill_install_error", str(exc))
    except Exception as exc:
        _err(HTTPStatus.INTERNAL_SERVER_ERROR, "skill_install_error", str(exc))


def uninstall_skill(service: Any, payload: Any, skill_id: str = "", **kw: Any):
    removed = service.skill_registry.uninstall(skill_id)
    if not removed:
        _err(HTTPStatus.NOT_FOUND, "skill_not_found", f"Skill '{skill_id}' not found.")
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("integration_changed", {"action": "skill_uninstalled", "skill_id": skill_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, {"status": "success", "removed": skill_id})
