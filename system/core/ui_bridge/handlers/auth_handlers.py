"""Authentication route handlers: setup, login, user CRUD, token introspection."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any


def _get_auth_plugin(service: Any):
    """Resolve the auth plugin from the service container."""
    plugin = service.container.get_plugin("capos.core.auth")
    if plugin is None:
        from system.core.ui_bridge.api_server import APIRequestError
        raise APIRequestError(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "auth_not_available",
            "Authentication plugin is not loaded.",
        )
    return plugin


def _get_user_payload(service: Any, **kw: Any) -> dict[str, Any]:
    """Extract and validate the JWT from the current request headers."""
    from system.core.ui_bridge.api_server import APIRequestError
    from system.core.auth import AuthMiddleware

    plugin = _get_auth_plugin(service)
    headers = kw.get("_headers", {})
    payload = AuthMiddleware.authenticate_request(headers, plugin.jwt_service)
    if payload is None:
        raise APIRequestError(
            HTTPStatus.UNAUTHORIZED,
            "unauthorized",
            "Missing or invalid authentication token.",
        )
    return payload


def _require_role(user_payload: dict[str, Any], required_role: str) -> None:
    """Raise if the user does not meet the required role."""
    from system.core.ui_bridge.api_server import APIRequestError
    from system.core.auth import AuthMiddleware

    if not AuthMiddleware.check_permission(user_payload, required_role):
        raise APIRequestError(
            HTTPStatus.FORBIDDEN,
            "forbidden",
            f"This action requires at least '{required_role}' role.",
        )


# ======================================================================
# POST /auth/setup — first-time owner creation
# ======================================================================

def auth_setup(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse, APIRequestError

    plugin = _get_auth_plugin(service)
    body = payload or {}

    if plugin.user_registry.has_owner():
        raise APIRequestError(
            HTTPStatus.CONFLICT,
            "owner_exists",
            "An owner account already exists. Use /auth/login instead.",
        )

    username = body.get("username", "").strip()
    password = body.get("password", "")
    display_name = body.get("display_name", "").strip()

    if not username or not password:
        raise APIRequestError(
            HTTPStatus.BAD_REQUEST,
            "missing_fields",
            "Both 'username' and 'password' are required.",
        )

    if len(password) < 6:
        raise APIRequestError(
            HTTPStatus.BAD_REQUEST,
            "weak_password",
            "Password must be at least 6 characters.",
        )

    user = plugin.user_registry.create_user(
        username=username,
        password=password,
        display_name=display_name or username,
        role="owner",
    )
    token = plugin.jwt_service.create_token(user["id"], user["role"])

    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("auth_setup_complete", {"user_id": user["id"]})
    except Exception:
        pass

    return APIResponse(HTTPStatus.CREATED, {"token": token, "user": user})


# ======================================================================
# POST /auth/login
# ======================================================================

def auth_login(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse, APIRequestError

    plugin = _get_auth_plugin(service)
    body = payload or {}

    username = body.get("username", "").strip()
    password = body.get("password", "")

    if not username or not password:
        raise APIRequestError(
            HTTPStatus.BAD_REQUEST,
            "missing_fields",
            "Both 'username' and 'password' are required.",
        )

    user = plugin.user_registry.authenticate(username, password)
    if user is None:
        raise APIRequestError(
            HTTPStatus.UNAUTHORIZED,
            "invalid_credentials",
            "Invalid username or password.",
        )

    token = plugin.jwt_service.create_token(user["id"], user["role"])
    return APIResponse(HTTPStatus.OK, {"token": token, "user": user})


# ======================================================================
# GET /auth/me — current user from token
# ======================================================================

def auth_me(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse, APIRequestError

    user_payload = _get_user_payload(service, **kw)
    plugin = _get_auth_plugin(service)

    user = plugin.user_registry.get_user(user_payload["user_id"])
    if user is None:
        raise APIRequestError(
            HTTPStatus.NOT_FOUND,
            "user_not_found",
            "User account no longer exists.",
        )

    return APIResponse(HTTPStatus.OK, {"user": user})


# ======================================================================
# GET /auth/users — list all users (owner/admin only)
# ======================================================================

def list_users(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse

    user_payload = _get_user_payload(service, **kw)
    _require_role(user_payload, "admin")

    plugin = _get_auth_plugin(service)
    users = plugin.user_registry.list_users()
    return APIResponse(HTTPStatus.OK, {"users": users})


# ======================================================================
# POST /auth/users — create a new user (owner/admin only)
# ======================================================================

def create_user(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse, APIRequestError

    user_payload = _get_user_payload(service, **kw)
    _require_role(user_payload, "admin")

    plugin = _get_auth_plugin(service)
    body = payload or {}

    username = body.get("username", "").strip()
    password = body.get("password", "")
    display_name = body.get("display_name", "").strip()
    role = body.get("role", "user")
    permissions = body.get("permissions")

    if not username or not password:
        raise APIRequestError(
            HTTPStatus.BAD_REQUEST,
            "missing_fields",
            "Both 'username' and 'password' are required.",
        )

    if len(password) < 6:
        raise APIRequestError(
            HTTPStatus.BAD_REQUEST,
            "weak_password",
            "Password must be at least 6 characters.",
        )

    # Only owners can create admins/owners
    if role in ("owner", "admin") and user_payload.get("role") != "owner":
        raise APIRequestError(
            HTTPStatus.FORBIDDEN,
            "forbidden",
            "Only the owner can create admin or owner accounts.",
        )

    try:
        user = plugin.user_registry.create_user(
            username=username,
            password=password,
            display_name=display_name or username,
            role=role,
            permissions=permissions,
        )
    except ValueError as exc:
        raise APIRequestError(
            HTTPStatus.BAD_REQUEST,
            "validation_error",
            str(exc),
        )

    return APIResponse(HTTPStatus.CREATED, {"user": user})


# ======================================================================
# PUT /auth/users/{user_id} — update a user (owner/admin only)
# ======================================================================

def update_user(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse, APIRequestError

    user_payload = _get_user_payload(service, **kw)
    _require_role(user_payload, "admin")

    plugin = _get_auth_plugin(service)
    user_id = kw.get("user_id", "")
    body = payload or {}

    # Only owners can change roles to admin/owner
    new_role = body.get("role")
    if new_role in ("owner", "admin") and user_payload.get("role") != "owner":
        raise APIRequestError(
            HTTPStatus.FORBIDDEN,
            "forbidden",
            "Only the owner can assign admin or owner roles.",
        )

    # Validate password length if being changed
    if "password" in body and len(body["password"]) < 6:
        raise APIRequestError(
            HTTPStatus.BAD_REQUEST,
            "weak_password",
            "Password must be at least 6 characters.",
        )

    try:
        updated = plugin.user_registry.update_user(user_id, **body)
    except ValueError as exc:
        raise APIRequestError(
            HTTPStatus.BAD_REQUEST,
            "validation_error",
            str(exc),
        )

    if updated is None:
        raise APIRequestError(
            HTTPStatus.NOT_FOUND,
            "user_not_found",
            f"User '{user_id}' not found.",
        )

    return APIResponse(HTTPStatus.OK, {"user": updated})


# ======================================================================
# DELETE /auth/users/{user_id} — delete a user (owner only, can't self-delete)
# ======================================================================

def delete_user(service: Any, payload: Any, **kw: Any):
    from system.core.ui_bridge.api_server import APIResponse, APIRequestError

    user_payload = _get_user_payload(service, **kw)
    _require_role(user_payload, "owner")

    user_id = kw.get("user_id", "")

    if user_id == user_payload.get("user_id"):
        raise APIRequestError(
            HTTPStatus.BAD_REQUEST,
            "cannot_delete_self",
            "You cannot delete your own account.",
        )

    plugin = _get_auth_plugin(service)
    deleted = plugin.user_registry.delete_user(user_id)

    if not deleted:
        raise APIRequestError(
            HTTPStatus.NOT_FOUND,
            "user_not_found",
            f"User '{user_id}' not found.",
        )

    return APIResponse(HTTPStatus.OK, {"deleted": True, "user_id": user_id})
