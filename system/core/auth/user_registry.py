"""User registry — CRUD operations with bcrypt password hashing.

Users are persisted to ``workspace/users.json`` and all mutations are
thread-safe via an ``RLock``.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

import bcrypt

logger = logging.getLogger(__name__)

# Default permissions per role
_DEFAULT_PERMISSIONS: dict[str, dict[str, Any]] = {
    "owner": {
        "workspaces": "*",
        "agents": "*",
        "max_security_level": 10,
        "can_create_agents": True,
        "can_create_skills": True,
        "can_access_supervisor": True,
    },
    "admin": {
        "workspaces": "*",
        "agents": "*",
        "max_security_level": 7,
        "can_create_agents": True,
        "can_create_skills": True,
        "can_access_supervisor": True,
    },
    "user": {
        "workspaces": [],
        "agents": [],
        "max_security_level": 3,
        "can_create_agents": False,
        "can_create_skills": False,
        "can_access_supervisor": False,
    },
    "viewer": {
        "workspaces": [],
        "agents": [],
        "max_security_level": 0,
        "can_create_agents": False,
        "can_create_skills": False,
        "can_access_supervisor": False,
    },
}

VALID_ROLES = ("owner", "admin", "user", "viewer")


class UserRegistry:
    """Manages user accounts with bcrypt-hashed passwords.

    Parameters
    ----------
    storage_path:
        Path to the ``users.json`` file.  Parent directories are created
        automatically.
    """

    def __init__(self, storage_path: Path | str) -> None:
        self._path = Path(storage_path)
        self._lock = RLock()
        self._users: dict[str, dict[str, Any]] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._users = data
                    logger.info("Loaded %d users from %s", len(self._users), self._path)
            except Exception:
                logger.exception("Failed to load users from %s", self._path)
                self._users = {}
        else:
            self._users = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._users, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def has_owner(self) -> bool:
        """Return ``True`` if at least one owner account exists."""
        with self._lock:
            return any(u.get("role") == "owner" for u in self._users.values())

    def create_user(
        self,
        username: str,
        password: str,
        display_name: str = "",
        role: str = "user",
        permissions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new user.  The *first* user created is always ``owner``."""
        with self._lock:
            # Force first user to be owner
            if not self._users:
                role = "owner"

            if role not in VALID_ROLES:
                raise ValueError(f"Invalid role '{role}'. Must be one of {VALID_ROLES}")

            # Uniqueness check on username
            for u in self._users.values():
                if u["username"] == username:
                    raise ValueError(f"Username '{username}' already exists")

            user_id = f"usr_{uuid.uuid4().hex[:12]}"
            password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

            merged_permissions = dict(_DEFAULT_PERMISSIONS.get(role, {}))
            if permissions:
                merged_permissions.update(permissions)

            user = {
                "id": user_id,
                "username": username,
                "display_name": display_name or username,
                "password_hash": password_hash,
                "role": role,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "permissions": merged_permissions,
            }

            self._users[user_id] = user
            self._save()
            logger.info("Created user %s (%s) with role=%s", username, user_id, role)
            return self._safe_user(user)

    def authenticate(self, username: str, password: str) -> dict[str, Any] | None:
        """Verify credentials.  Returns the user dict (without hash) or ``None``."""
        with self._lock:
            for u in self._users.values():
                if u["username"] == username:
                    stored_hash = u["password_hash"]
                    if bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8")):
                        return self._safe_user(u)
                    return None
            return None

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        """Fetch a single user by id."""
        with self._lock:
            user = self._users.get(user_id)
            return self._safe_user(user) if user else None

    def list_users(self) -> list[dict[str, Any]]:
        """Return all users (without password hashes)."""
        with self._lock:
            return [self._safe_user(u) for u in self._users.values()]

    def update_user(self, user_id: str, **fields: Any) -> dict[str, Any] | None:
        """Update mutable fields on an existing user.

        Allowed fields: ``display_name``, ``role``, ``permissions``, ``password``.
        If ``password`` is supplied it is re-hashed before storage.
        """
        with self._lock:
            user = self._users.get(user_id)
            if user is None:
                return None

            if "password" in fields:
                raw = fields.pop("password")
                user["password_hash"] = bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

            if "username" in fields:
                new_name = fields["username"]
                for uid, u in self._users.items():
                    if u["username"] == new_name and uid != user_id:
                        raise ValueError(f"Username '{new_name}' already exists")

            allowed = {"display_name", "role", "permissions", "username"}
            for key, value in fields.items():
                if key in allowed:
                    if key == "role" and value not in VALID_ROLES:
                        raise ValueError(f"Invalid role '{value}'")
                    user[key] = value

            self._save()
            return self._safe_user(user)

    def delete_user(self, user_id: str) -> bool:
        """Remove a user.  Returns ``True`` if deleted."""
        with self._lock:
            if user_id in self._users:
                del self._users[user_id]
                self._save()
                logger.info("Deleted user %s", user_id)
                return True
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_user(user: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of the user dict with the password hash stripped."""
        return {k: v for k, v in user.items() if k != "password_hash"}
