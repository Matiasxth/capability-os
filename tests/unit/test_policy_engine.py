"""Tests for the Policy Engine."""

import json
import pytest
from system.sdk.policy import PolicyEngine, PolicyRule, PolicyDecision


@pytest.fixture
def default_engine():
    """Engine with standard builtin/external/role rules."""
    rules = [
        {"id": "builtin-all", "description": "Builtins allowed", "target": {"tags": ["builtin"]}, "permissions": ["*"], "effect": "allow", "priority": 100},
        {"id": "external-deny-exec", "description": "External no exec", "target": {"tags": ["external"]}, "permissions": ["execution.*"], "effect": "deny", "priority": 90},
        {"id": "external-allow-read", "description": "External can read", "target": {"tags": ["external"]}, "permissions": ["filesystem.read", "memory.read"], "effect": "allow", "priority": 80},
        {"id": "viewer-deny-write", "description": "Viewer no write", "target": {"user_roles": ["viewer"]}, "permissions": ["filesystem.write", "execution.*"], "effect": "deny", "priority": 70},
        {"id": "owner-all", "description": "Owner full", "target": {"user_roles": ["owner"]}, "permissions": ["*"], "effect": "allow", "priority": 50},
    ]
    return PolicyEngine(rules=rules, default_effect="deny")


class TestPolicyEvaluation:
    def test_builtin_plugin_allowed(self, default_engine):
        decision = default_engine.evaluate("execution.subprocess", plugin_tags=["builtin"])
        assert decision["allowed"] is True
        assert decision["rule_id"] == "builtin-all"

    def test_external_plugin_denied_exec(self, default_engine):
        decision = default_engine.evaluate("execution.subprocess", plugin_tags=["external"])
        assert decision["allowed"] is False
        assert decision["rule_id"] == "external-deny-exec"

    def test_external_plugin_allowed_read(self, default_engine):
        decision = default_engine.evaluate("filesystem.read", plugin_tags=["external"])
        assert decision["allowed"] is True
        assert decision["rule_id"] == "external-allow-read"

    def test_external_plugin_denied_write_by_default(self, default_engine):
        decision = default_engine.evaluate("filesystem.write", plugin_tags=["external"])
        assert decision["allowed"] is False  # default deny, no rule matches

    def test_viewer_denied_write(self, default_engine):
        decision = default_engine.evaluate("filesystem.write", user_role="viewer")
        assert decision["allowed"] is False

    def test_owner_allowed_everything(self, default_engine):
        decision = default_engine.evaluate("execution.subprocess", user_role="owner")
        assert decision["allowed"] is True

    def test_default_deny(self, default_engine):
        decision = default_engine.evaluate("unknown.permission")
        assert decision["allowed"] is False
        assert decision["rule_id"] is None
        assert "default" in decision["reason"]

    def test_default_allow_engine(self):
        engine = PolicyEngine(rules=[], default_effect="allow")
        decision = engine.evaluate("anything")
        assert decision["allowed"] is True


class TestPriorityOrdering:
    def test_higher_priority_wins(self):
        rules = [
            {"id": "deny", "description": "Deny", "target": {}, "permissions": ["*"], "effect": "deny", "priority": 10},
            {"id": "allow", "description": "Allow", "target": {}, "permissions": ["*"], "effect": "allow", "priority": 20},
        ]
        engine = PolicyEngine(rules=rules)
        decision = engine.evaluate("filesystem.read")
        assert decision["allowed"] is True
        assert decision["rule_id"] == "allow"

    def test_lower_priority_loses(self):
        rules = [
            {"id": "allow", "description": "Allow", "target": {}, "permissions": ["*"], "effect": "allow", "priority": 10},
            {"id": "deny", "description": "Deny", "target": {}, "permissions": ["*"], "effect": "deny", "priority": 20},
        ]
        engine = PolicyEngine(rules=rules)
        decision = engine.evaluate("filesystem.read")
        assert decision["allowed"] is False
        assert decision["rule_id"] == "deny"


class TestPluginPermissionCheck:
    def test_all_permissions_allowed(self, default_engine):
        denied = default_engine.check_plugin_permissions(
            "capos.core.settings",
            ["filesystem.read", "settings.read"],
            plugin_tags=["builtin"],
        )
        assert denied == []

    def test_some_permissions_denied(self, default_engine):
        denied = default_engine.check_plugin_permissions(
            "external.plugin",
            ["filesystem.read", "execution.subprocess"],
            plugin_tags=["external"],
        )
        assert len(denied) == 1
        assert "execution.subprocess" in denied[0]


class TestRuleManagement:
    def test_add_rule(self):
        engine = PolicyEngine()
        engine.add_rule({"id": "new", "description": "New", "target": {}, "permissions": ["*"], "effect": "allow", "priority": 50})
        assert len(engine.rules) == 1

    def test_remove_rule(self):
        engine = PolicyEngine(rules=[
            {"id": "r1", "description": "R1", "target": {}, "permissions": ["*"], "effect": "allow", "priority": 50},
        ])
        assert engine.remove_rule("r1") is True
        assert len(engine.rules) == 0

    def test_remove_nonexistent(self):
        engine = PolicyEngine()
        assert engine.remove_rule("nope") is False


class TestAuditLog:
    def test_evaluation_creates_audit_entry(self, default_engine):
        default_engine.clear_audit_log()
        default_engine.evaluate("filesystem.read", plugin_id="test", user_role="owner")
        log = default_engine.audit_log
        assert len(log) == 1
        assert log[0]["permission"] == "filesystem.read"
        assert log[0]["plugin_id"] == "test"
        assert "timestamp" in log[0]

    def test_audit_log_capped(self):
        engine = PolicyEngine(rules=[
            {"id": "a", "description": "", "target": {}, "permissions": ["*"], "effect": "allow", "priority": 1},
        ])
        for _ in range(300):
            engine.evaluate("test.perm")
        assert len(engine.audit_log) <= 200


class TestFromFile:
    def test_load_policies_json(self, tmp_path):
        policy_file = tmp_path / "policies.json"
        policy_file.write_text(json.dumps({
            "version": "1.0.0",
            "default_effect": "allow",
            "rules": [
                {"id": "r1", "description": "Test", "target": {}, "permissions": ["*"], "effect": "deny", "priority": 1}
            ],
        }))
        engine = PolicyEngine.from_file(policy_file)
        assert len(engine.rules) == 1
        decision = engine.evaluate("anything")
        assert decision["allowed"] is False

    def test_missing_file_returns_empty(self, tmp_path):
        engine = PolicyEngine.from_file(tmp_path / "nonexistent.json")
        assert len(engine.rules) == 0

    def test_load_real_policies(self):
        from pathlib import Path
        policies_path = Path("system/core/security/policies.json")
        if policies_path.exists():
            engine = PolicyEngine.from_file(policies_path)
            assert len(engine.rules) >= 5
            # Verify builtin plugins get full access
            decision = engine.evaluate("execution.subprocess", plugin_tags=["builtin"])
            assert decision["allowed"] is True
