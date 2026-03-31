"""Permission scopes for the plugin system.

Plugins declare permissions they need in their manifest. The PolicyEngine
evaluates whether a plugin is allowed to use each permission based on rules.

Permissions are hierarchical: ``"filesystem.write"`` is a child of ``"filesystem"``.
A wildcard ``"filesystem.*"`` grants all filesystem permissions.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Permission tree — all valid permission scopes
# ---------------------------------------------------------------------------

PERMISSION_TREE: dict[str, list[str]] = {
    "filesystem": ["read", "write", "delete", "create_directory"],
    "network": ["http", "websocket", "dns"],
    "execution": ["subprocess", "docker", "script"],
    "browser": ["navigate", "screenshot", "interact", "read_text"],
    "memory": ["read", "write", "semantic", "markdown"],
    "event_bus": ["emit", "subscribe"],
    "settings": ["read", "write"],
    "users": ["read", "manage"],
    "plugins": ["install", "reload", "configure"],
    "workspaces": ["read", "write", "delete"],
    "agents": ["read", "write", "execute"],
    "capabilities": ["read", "register", "execute"],
    "tools": ["read", "register", "execute"],
    "scheduler": ["read", "create", "delete", "run"],
    "workflows": ["read", "create", "execute"],
    "mcp": ["servers", "tools"],
    "a2a": ["agents", "delegate"],
    "supervisor": ["invoke", "health", "approve"],
    "voice": ["transcribe", "synthesize"],
}


def all_permissions() -> list[str]:
    """Return all valid permission strings."""
    result = []
    for category, scopes in PERMISSION_TREE.items():
        result.append(f"{category}.*")
        for scope in scopes:
            result.append(f"{category}.{scope}")
    return sorted(result)


def is_valid_permission(permission: str) -> bool:
    """Check if a permission string is recognized."""
    if permission == "*":
        return True
    parts = permission.split(".", 1)
    if len(parts) != 2:
        return parts[0] in PERMISSION_TREE
    category, scope = parts
    if category not in PERMISSION_TREE:
        return False
    return scope == "*" or scope in PERMISSION_TREE[category]


def permission_matches(declared: str, required: str) -> bool:
    """Check if a declared permission covers a required permission.

    Examples:
        permission_matches("*", "filesystem.read") → True
        permission_matches("filesystem.*", "filesystem.read") → True
        permission_matches("filesystem.read", "filesystem.read") → True
        permission_matches("filesystem.read", "filesystem.write") → False
    """
    if declared == "*":
        return True
    if declared == required:
        return True
    # Wildcard: "filesystem.*" matches "filesystem.read"
    if declared.endswith(".*"):
        prefix = declared[:-2]
        return required.startswith(prefix + ".")
    return False


def validate_permissions(permissions: list[str]) -> list[str]:
    """Return list of invalid permission strings."""
    return [p for p in permissions if not is_valid_permission(p)]
