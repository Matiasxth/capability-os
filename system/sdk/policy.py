"""Policy Engine — evaluates permissions for plugins, users, and workspaces.

The engine matches requests against a priority-ordered rule set. Rules can
target specific plugins (by ID or tag), user roles, or workspaces. The first
matching rule wins; if no rule matches, the default effect applies.

Usage::

    engine = PolicyEngine.from_file("policies.json")
    decision = engine.evaluate("filesystem.write", plugin_id="my.plugin")
    if not decision["allowed"]:
        raise PermissionDeniedError(...)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from system.sdk.permissions import permission_matches

try:
    from typing import NotRequired
except ImportError:
    from typing_extensions import NotRequired

from typing import TypedDict

logger = logging.getLogger("capos.policy")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class PolicyTarget(TypedDict, total=False):
    """Who a policy rule applies to."""
    plugin_ids: list[str]       # specific plugin IDs
    user_roles: list[str]       # specific user roles
    workspace_ids: list[str]    # specific workspace IDs
    tags: list[str]             # plugin tags (e.g. "builtin", "external")


class PolicyRule(TypedDict):
    """A single policy rule."""
    id: str
    description: str
    target: PolicyTarget
    permissions: list[str]      # permission scopes this rule covers
    effect: str                 # "allow" | "deny"
    priority: int               # higher = evaluated first


class PolicyDecision(TypedDict):
    """Result of a policy evaluation."""
    allowed: bool
    rule_id: str | None
    reason: str


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class PolicyEngine:
    """Evaluates permission requests against a rule set."""

    def __init__(
        self,
        rules: list[PolicyRule] | None = None,
        default_effect: str = "deny",
    ) -> None:
        self._rules = sorted(rules or [], key=lambda r: -r.get("priority", 0))
        self._default = default_effect
        self._audit_log: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @classmethod
    def from_file(cls, path: str | Path) -> PolicyEngine:
        """Load policy rules from a JSON file."""
        p = Path(path)
        if not p.exists():
            logger.warning(f"Policy file not found: {p} — using empty ruleset")
            return cls()
        data = json.loads(p.read_text(encoding="utf-8"))
        rules = data.get("rules", [])
        default = data.get("default_effect", "deny")
        return cls(rules=rules, default_effect=default)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyEngine:
        """Load from a dict (e.g., from settings)."""
        return cls(
            rules=data.get("rules", []),
            default_effect=data.get("default_effect", "deny"),
        )

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        permission: str,
        plugin_id: str = "",
        user_role: str = "",
        workspace_id: str = "",
        plugin_tags: list[str] | None = None,
    ) -> PolicyDecision:
        """Evaluate whether an action is allowed.

        Iterates rules in priority order. First matching rule determines the outcome.
        If no rule matches, the default effect applies.
        """
        tags = plugin_tags or []

        for rule in self._rules:
            if not self._rule_covers_permission(rule, permission):
                continue
            if not self._rule_matches_target(rule, plugin_id, user_role, workspace_id, tags):
                continue

            decision = PolicyDecision(
                allowed=rule["effect"] == "allow",
                rule_id=rule["id"],
                reason=rule.get("description", ""),
            )
            self._record(permission, plugin_id, user_role, decision)
            return decision

        decision = PolicyDecision(
            allowed=self._default == "allow",
            rule_id=None,
            reason="default policy",
        )
        self._record(permission, plugin_id, user_role, decision)
        return decision

    def check_plugin_permissions(
        self,
        plugin_id: str,
        declared_permissions: list[str],
        plugin_tags: list[str] | None = None,
    ) -> list[str]:
        """Verify all declared permissions are allowed by policy.

        Returns list of denied permissions (empty = all allowed).
        """
        denied = []
        for perm in declared_permissions:
            decision = self.evaluate(perm, plugin_id=plugin_id, plugin_tags=plugin_tags)
            if not decision["allowed"]:
                denied.append(f"{perm}: {decision['reason']}")
        return denied

    # ------------------------------------------------------------------
    # Rules management
    # ------------------------------------------------------------------

    @property
    def rules(self) -> list[PolicyRule]:
        return list(self._rules)

    def add_rule(self, rule: PolicyRule) -> None:
        """Add a rule and re-sort by priority."""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: -r.get("priority", 0))

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a rule by ID. Returns True if found."""
        before = len(self._rules)
        self._rules = [r for r in self._rules if r["id"] != rule_id]
        return len(self._rules) < before

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    @property
    def audit_log(self) -> list[dict[str, Any]]:
        return self._audit_log[-200:]

    def clear_audit_log(self) -> None:
        self._audit_log.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _rule_covers_permission(rule: PolicyRule, permission: str) -> bool:
        """Check if rule's permission list covers the requested permission."""
        for rule_perm in rule.get("permissions", []):
            if permission_matches(rule_perm, permission):
                return True
        return False

    @staticmethod
    def _rule_matches_target(
        rule: PolicyRule,
        plugin_id: str,
        user_role: str,
        workspace_id: str,
        plugin_tags: list[str],
    ) -> bool:
        """Check if the rule's target matches the request context."""
        target = rule.get("target", {})
        if not target:
            return True  # No target = applies to everyone

        matched_any_criterion = False

        # Plugin ID match
        target_plugins = target.get("plugin_ids")
        if target_plugins is not None:
            if plugin_id and plugin_id in target_plugins:
                matched_any_criterion = True
            elif plugin_id and plugin_id not in target_plugins:
                return False

        # User role match
        target_roles = target.get("user_roles")
        if target_roles is not None:
            if user_role and user_role in target_roles:
                matched_any_criterion = True
            elif user_role and user_role not in target_roles:
                return False

        # Workspace match
        target_ws = target.get("workspace_ids")
        if target_ws is not None:
            if workspace_id and workspace_id in target_ws:
                matched_any_criterion = True
            elif workspace_id and workspace_id not in target_ws:
                return False

        # Tag match
        target_tags = target.get("tags")
        if target_tags is not None:
            if any(t in plugin_tags for t in target_tags):
                matched_any_criterion = True
            elif plugin_tags:
                return False

        # If target had criteria and none matched, don't apply
        has_criteria = any(
            target.get(k) is not None
            for k in ("plugin_ids", "user_roles", "workspace_ids", "tags")
        )
        return matched_any_criterion or not has_criteria

    def _record(
        self,
        permission: str,
        plugin_id: str,
        user_role: str,
        decision: PolicyDecision,
    ) -> None:
        """Record an audit entry."""
        self._audit_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "permission": permission,
            "plugin_id": plugin_id,
            "user_role": user_role,
            "allowed": decision["allowed"],
            "rule_id": decision["rule_id"],
            "reason": decision["reason"],
        })
        if len(self._audit_log) > 5000:
            self._audit_log = self._audit_log[-2500:]
