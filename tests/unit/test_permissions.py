"""Tests for the SDK permissions system."""

from system.sdk.permissions import (
    all_permissions,
    is_valid_permission,
    permission_matches,
    validate_permissions,
    PERMISSION_TREE,
)


class TestPermissionTree:
    def test_tree_has_categories(self):
        assert "filesystem" in PERMISSION_TREE
        assert "network" in PERMISSION_TREE
        assert "execution" in PERMISSION_TREE
        assert "browser" in PERMISSION_TREE
        assert "memory" in PERMISSION_TREE

    def test_categories_have_scopes(self):
        assert "read" in PERMISSION_TREE["filesystem"]
        assert "write" in PERMISSION_TREE["filesystem"]
        assert "http" in PERMISSION_TREE["network"]
        assert "subprocess" in PERMISSION_TREE["execution"]


class TestIsValidPermission:
    def test_wildcard(self):
        assert is_valid_permission("*") is True

    def test_category_wildcard(self):
        assert is_valid_permission("filesystem.*") is True

    def test_full_permission(self):
        assert is_valid_permission("filesystem.read") is True
        assert is_valid_permission("network.http") is True
        assert is_valid_permission("execution.subprocess") is True

    def test_invalid_category(self):
        assert is_valid_permission("unknown.read") is False

    def test_invalid_scope(self):
        assert is_valid_permission("filesystem.teleport") is False

    def test_category_only(self):
        assert is_valid_permission("filesystem") is True

    def test_empty(self):
        assert is_valid_permission("") is False


class TestPermissionMatches:
    def test_global_wildcard(self):
        assert permission_matches("*", "filesystem.read") is True
        assert permission_matches("*", "network.http") is True

    def test_category_wildcard(self):
        assert permission_matches("filesystem.*", "filesystem.read") is True
        assert permission_matches("filesystem.*", "filesystem.write") is True
        assert permission_matches("filesystem.*", "network.http") is False

    def test_exact_match(self):
        assert permission_matches("filesystem.read", "filesystem.read") is True
        assert permission_matches("filesystem.read", "filesystem.write") is False

    def test_no_partial_match(self):
        assert permission_matches("file", "filesystem.read") is False


class TestValidatePermissions:
    def test_all_valid(self):
        assert validate_permissions(["filesystem.read", "network.http"]) == []

    def test_some_invalid(self):
        invalid = validate_permissions(["filesystem.read", "magic.spell", "network.http"])
        assert invalid == ["magic.spell"]

    def test_empty(self):
        assert validate_permissions([]) == []


class TestAllPermissions:
    def test_returns_sorted_list(self):
        perms = all_permissions()
        assert len(perms) > 20
        assert perms == sorted(perms)
        assert "filesystem.read" in perms
        assert "filesystem.*" in perms


class TestManifestV2Fields:
    def test_manifest_accepts_permissions(self):
        from system.sdk.manifest import PluginManifest  # noqa: F811
        m = PluginManifest.from_dict({
            "id": "test.plugin",
            "name": "Test",
            "version": "1.0.0",
            "permissions": ["filesystem.read", "network.http"],
            "provided_services": ["SomeContract"],
            "events_emitted": ["test_event"],
            "tags": ["builtin"],
            "license": "MIT",
        })
        assert m.permissions == ["filesystem.read", "network.http"]
        assert m.provided_services == ["SomeContract"]
        assert m.events_emitted == ["test_event"]
        assert m.tags == ["builtin"]
        assert m.license == "MIT"

    def test_manifest_defaults(self):
        from system.sdk.manifest import PluginManifest
        m = PluginManifest.from_dict({
            "id": "test.plugin",
            "name": "Test",
            "version": "1.0.0",
        })
        assert m.permissions == []
        assert m.provided_services == []
        assert m.events_emitted == []
        assert m.tags == []
        assert m.license == ""
        assert m.config_schema == {}

    def test_manifest_roundtrip(self):
        from system.sdk.manifest import PluginManifest
        m = PluginManifest.from_dict({
            "id": "test.plugin",
            "name": "Test",
            "version": "1.0.0",
            "permissions": ["filesystem.*"],
            "tags": ["external"],
        })
        d = m.to_dict()
        assert d["permissions"] == ["filesystem.*"]
        assert d["tags"] == ["external"]
        m2 = PluginManifest.from_dict(d)
        assert m2.permissions == m.permissions
