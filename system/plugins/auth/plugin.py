"""Auth plugin — provides UserRegistry, JWTService, and AuthMiddleware.

Dependencies: capos.core.settings (needs workspace_root for storage paths).
"""
from __future__ import annotations

import logging
from typing import Any

from system.sdk.context import PluginContext

logger = logging.getLogger(__name__)


class AuthPlugin:
    """Bootstraps authentication services and publishes them to the container."""

    plugin_id: str = "capos.core.auth"
    plugin_name: str = "Authentication"
    version: str = "1.0.0"
    dependencies: list[str] = ["capos.core.settings"]

    def __init__(self) -> None:
        self.user_registry: Any = None
        self.jwt_service: Any = None
        self.auth_middleware: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize(self, ctx: PluginContext) -> None:
        from system.core.auth import UserRegistry, JWTService, AuthMiddleware

        workspace_root = ctx.workspace_root

        # --- UserRegistry ---
        users_path = workspace_root / "users.json"
        self.user_registry = UserRegistry(storage_path=users_path)
        logger.info(
            "UserRegistry initialized (%d users, owner=%s)",
            len(self.user_registry.list_users()),
            self.user_registry.has_owner(),
        )

        # --- JWTService ---
        secret_path = workspace_root / "jwt_secret.key"
        self.jwt_service = JWTService(secret_path=secret_path)
        logger.info("JWTService initialized")

        # --- AuthMiddleware (stateless, but exposed for convenience) ---
        self.auth_middleware = AuthMiddleware()
        logger.info("AuthMiddleware ready")

    def register_routes(self, router) -> None:
        from system.core.ui_bridge.handlers import auth_handlers
        router.add("GET", "/auth/status", auth_handlers.auth_status)
        router.add("POST", "/auth/setup", auth_handlers.auth_setup)
        router.add("POST", "/auth/login", auth_handlers.auth_login)
        router.add("GET", "/auth/me", auth_handlers.auth_me)
        router.add("GET", "/auth/users", auth_handlers.list_users)
        router.add("POST", "/auth/users", auth_handlers.create_user)
        router.add("PUT", "/auth/users/{user_id}", auth_handlers.update_user)
        router.add("DELETE", "/auth/users/{user_id}", auth_handlers.delete_user)

    def start(self) -> None:
        """Auth services are passive — nothing to start."""

    def stop(self) -> None:
        """Auth services are passive — nothing to stop."""


# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

def create_plugin() -> AuthPlugin:
    """Entry-point factory used by the plugin loader."""
    return AuthPlugin()
