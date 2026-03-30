"""Request-level authentication helpers.

Provides extraction of Bearer tokens from headers, validation via
:class:`JWTService`, and role-based permission checks.
"""
from __future__ import annotations

from typing import Any

from .jwt_service import JWTService

# Role hierarchy — higher index means more privilege.
_ROLE_HIERARCHY: dict[str, int] = {
    "viewer": 0,
    "user": 1,
    "admin": 2,
    "owner": 3,
}

# Paths that never require authentication.
PUBLIC_PATHS: set[str] = {
    "/auth/login",
    "/auth/setup",
    "/status",
}


class AuthMiddleware:
    """Stateless helper bundle for request authentication."""

    # ------------------------------------------------------------------
    # Token extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_token(headers: dict[str, str]) -> str | None:
        """Pull the JWT from an ``Authorization: Bearer <token>`` header.

        The lookup is case-insensitive on the header name.
        """
        for key, value in headers.items():
            if key.lower() == "authorization":
                parts = value.split()
                if len(parts) == 2 and parts[0].lower() == "bearer":
                    return parts[1]
        return None

    # ------------------------------------------------------------------
    # Full request authentication
    # ------------------------------------------------------------------

    @staticmethod
    def authenticate_request(
        headers: dict[str, str],
        jwt_service: JWTService,
    ) -> dict[str, Any] | None:
        """Validate the request and return the decoded JWT payload.

        Returns ``None`` if no valid token is present.
        """
        token = AuthMiddleware.extract_token(headers)
        if token is None:
            return None
        return jwt_service.validate_token(token)

    # ------------------------------------------------------------------
    # Permission checks
    # ------------------------------------------------------------------

    @staticmethod
    def check_permission(
        user_payload: dict[str, Any],
        required_role: str,
    ) -> bool:
        """Return ``True`` if the user's role meets or exceeds *required_role*."""
        user_level = _ROLE_HIERARCHY.get(user_payload.get("role", ""), -1)
        required_level = _ROLE_HIERARCHY.get(required_role, 999)
        return user_level >= required_level

    # ------------------------------------------------------------------
    # Public-path helper
    # ------------------------------------------------------------------

    @staticmethod
    def is_public_path(method: str, path: str) -> bool:
        """Check whether a request should bypass authentication."""
        if method.upper() == "OPTIONS":
            return True
        clean = path.rstrip("/") or "/"
        return clean in PUBLIC_PATHS
