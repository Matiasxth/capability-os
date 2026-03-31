"""Tests for the Audit Logger."""

from system.sdk.audit import AuditLogger


class TestAuditLog:
    def test_log_entry(self):
        logger = AuditLogger()
        logger.log("policy_decision", plugin_id="test", permission="fs.read", allowed=True)
        assert logger.total_entries == 1
        assert logger.recent[0]["event"] == "policy_decision"
        assert logger.recent[0]["plugin_id"] == "test"

    def test_log_policy_decision(self):
        logger = AuditLogger()
        logger.log_policy_decision("fs.write", plugin_id="ext", allowed=False, rule_id="r1", reason="denied")
        entries = logger.query(event="policy_decision")
        assert len(entries) == 1
        assert entries[0]["allowed"] is False
        assert "r1" in entries[0]["detail"]

    def test_log_service_access(self):
        logger = AuditLogger()
        logger.log_service_access("my.plugin", "AgentLoopContract", allowed=True)
        entries = logger.query(event="service_access")
        assert len(entries) == 1
        assert "AgentLoopContract" in entries[0]["permission"]

    def test_log_plugin_lifecycle(self):
        logger = AuditLogger()
        logger.log_plugin_lifecycle("my.plugin", "started")
        entries = logger.query(event="plugin_lifecycle")
        assert len(entries) == 1
        assert "started" in entries[0]["detail"]


class TestQuery:
    def test_filter_by_plugin(self):
        logger = AuditLogger()
        logger.log("a", plugin_id="p1")
        logger.log("a", plugin_id="p2")
        logger.log("a", plugin_id="p1")
        assert len(logger.query(plugin_id="p1")) == 2

    def test_filter_by_event(self):
        logger = AuditLogger()
        logger.log("policy_decision")
        logger.log("service_access")
        logger.log("policy_decision")
        assert len(logger.query(event="policy_decision")) == 2

    def test_filter_by_allowed(self):
        logger = AuditLogger()
        logger.log("a", allowed=True)
        logger.log("a", allowed=False)
        logger.log("a", allowed=False)
        assert len(logger.query(allowed=False)) == 2

    def test_limit(self):
        logger = AuditLogger()
        for i in range(20):
            logger.log("a", plugin_id=f"p{i}")
        assert len(logger.query(limit=5)) == 5

    def test_combined_filters(self):
        logger = AuditLogger()
        logger.log("policy_decision", plugin_id="p1", allowed=False)
        logger.log("policy_decision", plugin_id="p2", allowed=False)
        logger.log("service_access", plugin_id="p1", allowed=True)
        result = logger.query(plugin_id="p1", event="policy_decision")
        assert len(result) == 1


class TestSummary:
    def test_plugin_activity(self):
        logger = AuditLogger()
        logger.log("policy_decision", plugin_id="p1")
        logger.log("policy_decision", plugin_id="p1")
        logger.log("service_access", plugin_id="p1")
        activity = logger.get_plugin_activity("p1")
        assert activity["policy_decision"] == 2
        assert activity["service_access"] == 1

    def test_denied_summary(self):
        logger = AuditLogger()
        logger.log("a", plugin_id="bad", permission="fs.write", allowed=False)
        logger.log("a", plugin_id="bad", permission="exec.sub", allowed=False)
        logger.log("a", plugin_id="good", permission="fs.read", allowed=True)
        denied = logger.get_denied_summary()
        assert len(denied) == 1
        assert denied[0]["plugin_id"] == "bad"
        assert denied[0]["denied_count"] == 2


class TestCapacity:
    def test_max_entries_capped(self):
        logger = AuditLogger(max_entries=100)
        for i in range(200):
            logger.log("a", plugin_id=f"p{i}")
        assert logger.total_entries <= 100

    def test_clear(self):
        logger = AuditLogger()
        logger.log("a")
        logger.log("b")
        logger.clear()
        assert logger.total_entries == 0


class TestPolicyEngineIntegration:
    def test_policy_forwards_to_audit_logger(self):
        from system.sdk.policy import PolicyEngine
        audit = AuditLogger()
        engine = PolicyEngine(
            rules=[{"id": "r1", "description": "Allow all", "target": {}, "permissions": ["*"], "effect": "allow", "priority": 1}],
            audit_logger=audit,
        )
        engine.evaluate("filesystem.read", plugin_id="test")
        assert audit.total_entries == 1
        assert audit.recent[0]["event"] == "policy_decision"
        assert audit.recent[0]["allowed"] is True
