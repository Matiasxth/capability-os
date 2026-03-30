"""Authentication subsystem for Capability OS.

Provides user management, JWT tokens, and request-level auth middleware.
"""
from .user_registry import UserRegistry
from .jwt_service import JWTService
from .auth_middleware import AuthMiddleware

__all__ = ["UserRegistry", "JWTService", "AuthMiddleware"]
