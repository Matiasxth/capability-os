"""JWT token generation and validation using PyJWT.

The secret key is auto-generated on first run and persisted to
``workspace/jwt_secret.key`` so tokens survive restarts.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt

logger = logging.getLogger(__name__)


class JWTService:
    """Stateless JWT token helper backed by a persistent secret key.

    Parameters
    ----------
    secret_path:
        Path to the file that holds the HMAC secret.  Created automatically
        on first use.
    algorithm:
        JWT signing algorithm (default ``HS256``).
    """

    def __init__(
        self,
        secret_path: Path | str,
        algorithm: str = "HS256",
    ) -> None:
        self._secret_path = Path(secret_path)
        self._algorithm = algorithm
        self._secret = self._load_or_create_secret()

    # ------------------------------------------------------------------
    # Secret key management
    # ------------------------------------------------------------------

    def _load_or_create_secret(self) -> str:
        if self._secret_path.exists():
            secret = self._secret_path.read_text(encoding="utf-8").strip()
            if secret:
                logger.info("Loaded JWT secret from %s", self._secret_path)
                return secret

        secret = secrets.token_hex(64)
        self._secret_path.parent.mkdir(parents=True, exist_ok=True)
        self._secret_path.write_text(secret, encoding="utf-8")
        logger.info("Generated new JWT secret at %s", self._secret_path)
        return secret

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_token(
        self,
        user_id: str,
        role: str,
        expires_hours: int = 24,
    ) -> str:
        """Create a signed JWT containing *user_id* and *role*."""
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "user_id": user_id,
            "role": role,
            "iat": now,
            "exp": now + timedelta(hours=expires_hours),
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def validate_token(self, token: str) -> dict[str, Any] | None:
        """Decode and verify a JWT.

        Returns the payload dict (``user_id``, ``role``, ``exp``, ``iat``)
        or ``None`` if the token is invalid / expired.
        """
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                options={"require": ["user_id", "role", "exp"]},
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.debug("Token expired")
            return None
        except jwt.InvalidTokenError as exc:
            logger.debug("Invalid token: %s", exc)
            return None

    def refresh_token(self, token: str) -> str | None:
        """Return a fresh token if the given one is still valid, else ``None``."""
        payload = self.validate_token(token)
        if payload is None:
            return None
        return self.create_token(
            user_id=payload["user_id"],
            role=payload["role"],
        )
