"""
Tests for Bloque 4 — Integration System: 6 new components.

  1. IntegrationDetector — gap detection, listing, resolving.
  2. IntegrationClassifier — type classification from intent keywords.
  3. IntegrationPlanner — plan generation from gap + classification.
  4. TemplateEngine — manifest rendering, directory skeleton.
  5. IntegrationGenerator — on-disk scaffolding creation.
  6. CapabilityBridge — publishes integration capabilities into registry.
  7. Full pipeline — detector → classifier → planner → template → generator → bridge.
"""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from system.capabilities.registry import CapabilityRegistry
from system.integrations.bridge.capability_bridge import CapabilityBridge
from system.integrations.classifier.integration_classifier import IntegrationClassifier
from system.integrations.detector.integration_detector import IntegrationDetector
from system.integrations.generator.integration_generator import (
    IntegrationGenerator,
    IntegrationGeneratorError,
)
from system.integrations.planner.integration_planner import IntegrationPlanner
from system.integrations.templates.template_engine import TemplateEngine

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "bloque4_integration"


def _workspace(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


# ===========================================================================
# 1. Integration Detector
# ===========================================================================

class TestIntegrationDetector(unittest.TestCase):

    def test_record_gap(self):
        detector = IntegrationDetector()
        gap = detector.record_gap("send email via gmail", suggested_capability="send_gmail_email")
        self.assertIn("id", gap)
        self.assertEqual(gap["status"], "open")
        self.assertEqual(gap["intent"], "send email via gmail")
        self.assertEqual(gap["suggested_capability"], "send_gmail_email")

    def test_list_gaps_all(self):
        detector = IntegrationDetector()
        detector.record_gap("intent1")
        detector.record_gap("intent2")
        self.assertEqual(len(detector.list_gaps()), 2)

    def test_list_gaps_by_status(self):
        detector = IntegrationDetector()
        g1 = detector.record_gap("intent1")
        detector.record_gap("intent2")
        detector.resolve_gap(g1["id"], "some_connector")
        open_gaps = detector.list_gaps(status="open")
        self.assertEqual(len(open_gaps), 1)

    def test_resolve_gap(self):
        detector = IntegrationDetector()
        gap = detector.record_gap("intent")
        resolved = detector.resolve_gap(gap["id"], "test_connector")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["resolved_by"], "test_connector")

    def test_resolve_nonexistent_gap_returns_none(self):
        detector = IntegrationDetector()
        self.assertIsNone(detector.resolve_gap("nonexistent_id", "x"))

    def test_close_gap(self):
        detector = IntegrationDetector()
        gap = detector.record_gap("intent")
        closed = detector.close_gap(gap["id"], "not needed")
        self.assertEqual(closed["status"], "closed")

    def test_get_gap(self):
        detector = IntegrationDetector()
        gap = detector.record_gap("my intent")
        found = detector.get_gap(gap["id"])
        self.assertIsNotNone(found)
        self.assertEqual(found["intent"], "my intent")

    def test_open_gap_count(self):
        detector = IntegrationDetector()
        detector.record_gap("a")
        g2 = detector.record_gap("b")
        detector.resolve_gap(g2["id"], "x")
        self.assertEqual(detector.open_gap_count, 1)


# ===========================================================================
# 2. Integration Classifier
# ===========================================================================

class TestIntegrationClassifier(unittest.TestCase):

    def setUp(self):
        self.classifier = IntegrationClassifier()

    def test_classifies_web_app(self):
        result = self.classifier.classify("send a message via WhatsApp Web browser")
        self.assertEqual(result["integration_type"], "web_app")
        self.assertIn(result["confidence"], {"high", "medium"})

    def test_classifies_rest_api(self):
        result = self.classifier.classify("call the REST API endpoint to get JSON data")
        self.assertEqual(result["integration_type"], "rest_api")

    def test_classifies_local_app(self):
        result = self.classifier.classify("run local desktop app from terminal CLI")
        self.assertEqual(result["integration_type"], "local_app")

    def test_classifies_file_based(self):
        result = self.classifier.classify("import CSV file and export to Excel document")
        self.assertEqual(result["integration_type"], "file_based")

    def test_default_to_rest_api_on_no_keywords(self):
        result = self.classifier.classify("xyzzy foobar")
        self.assertEqual(result["integration_type"], "rest_api")
        self.assertEqual(result["confidence"], "low")

    def test_scores_present(self):
        result = self.classifier.classify("browser website page")
        self.assertIn("scores", result)
        self.assertIsInstance(result["scores"], dict)


# ===========================================================================
# 3. Integration Planner
# ===========================================================================

class TestIntegrationPlanner(unittest.TestCase):

    def setUp(self):
        self.planner = IntegrationPlanner()

    def test_plan_from_gap_and_classification(self):
        gap = {"id": "gap_123", "intent": "send slack message", "suggested_capability": "send_slack_message"}
        classification = {"integration_type": "rest_api", "confidence": "high"}
        plan = self.planner.plan(gap, classification)
        self.assertEqual(plan["integration_type"], "rest_api")
        self.assertIn("send_slack_message", plan["capabilities"])
        self.assertEqual(plan["status"], "proposed")
        self.assertEqual(plan["source_gap_id"], "gap_123")

    def test_plan_generates_id(self):
        gap = {"id": "gap_x", "intent": "send gmail email"}
        classification = {"integration_type": "rest_api"}
        plan = self.planner.plan(gap, classification)
        self.assertIn("api_connector", plan["integration_id"])

    def test_plan_with_web_app_type(self):
        gap = {"id": "gap_x", "intent": "browse twitter", "suggested_capability": None}
        classification = {"integration_type": "web_app"}
        plan = self.planner.plan(gap, classification)
        self.assertEqual(plan["integration_type"], "web_app")
        self.assertIn("browser", str(plan["requirements"]))

    def test_plan_default_capability_when_none_suggested(self):
        gap = {"id": "gap_x", "intent": "do something"}
        classification = {"integration_type": "file_based"}
        plan = self.planner.plan(gap, classification)
        self.assertTrue(len(plan["capabilities"]) > 0)


# ===========================================================================
# 4. Template Engine
# ===========================================================================

class TestTemplateEngine(unittest.TestCase):

    def setUp(self):
        self.engine = TemplateEngine()

    def test_render_manifest_web_app(self):
        plan = {"integration_id": "gmail_web_connector", "integration_type": "web_app", "capabilities": ["send_email"]}
        manifest = self.engine.render_manifest(plan)
        self.assertEqual(manifest["id"], "gmail_web_connector")
        self.assertEqual(manifest["type"], "web_app")
        self.assertEqual(manifest["status"], "not_configured")
        self.assertIn("send_email", manifest["capabilities"])

    def test_render_manifest_rest_api(self):
        plan = {"integration_id": "slack_api_connector", "integration_type": "rest_api", "capabilities": ["post_message"]}
        manifest = self.engine.render_manifest(plan)
        self.assertEqual(manifest["type"], "rest_api")

    def test_render_directory_list(self):
        plan = {"integration_id": "test_web_connector"}
        dirs = self.engine.render_directory_list(plan)
        self.assertIn("test_web_connector", dirs)
        self.assertIn("test_web_connector/capabilities", dirs)
        self.assertIn("test_web_connector/tools", dirs)
        self.assertIn("test_web_connector/config", dirs)
        self.assertIn("test_web_connector/tests", dirs)

    def test_render_manifest_name_auto_generated(self):
        plan = {"integration_id": "my_api_connector", "integration_type": "rest_api", "capabilities": ["x"]}
        manifest = self.engine.render_manifest(plan)
        self.assertEqual(manifest["name"], "My Api Connector")

    def test_plan_requirements_override_template(self):
        plan = {
            "integration_id": "test_api_connector",
            "integration_type": "rest_api",
            "capabilities": ["x"],
            "requirements": {"custom": True},
        }
        manifest = self.engine.render_manifest(plan)
        self.assertEqual(manifest["requirements"], {"custom": True})


# ===========================================================================
# 5. Integration Generator
# ===========================================================================

class TestIntegrationGenerator(unittest.TestCase):

    def test_generate_creates_structure(self):
        ws = _workspace("gen_basic")
        gen = IntegrationGenerator(ws)
        plan = {"integration_id": "test_api_connector", "integration_type": "rest_api", "capabilities": ["test_action"]}
        manifest = TemplateEngine().render_manifest(plan)
        result = gen.generate(plan, manifest)

        self.assertEqual(result["status"], "generated")
        self.assertTrue((ws / "test_api_connector" / "manifest.json").exists())
        self.assertTrue((ws / "test_api_connector" / "capabilities").is_dir())
        self.assertTrue((ws / "test_api_connector" / "tools").is_dir())
        self.assertTrue((ws / "test_api_connector" / "config").is_dir())
        self.assertTrue((ws / "test_api_connector" / "tests").is_dir())
        self.assertTrue((ws / "test_api_connector" / "__init__.py").exists())

        # Verify manifest content
        written = json.loads((ws / "test_api_connector" / "manifest.json").read_text())
        self.assertEqual(written["id"], "test_api_connector")
        self.assertEqual(written["type"], "rest_api")

    def test_generate_fails_if_dir_exists(self):
        ws = _workspace("gen_exists")
        (ws / "existing_api_connector").mkdir()
        gen = IntegrationGenerator(ws)
        plan = {"integration_id": "existing_api_connector", "integration_type": "rest_api", "capabilities": ["x"]}
        with self.assertRaises(IntegrationGeneratorError):
            gen.generate(plan)

    def test_generate_auto_renders_manifest_from_plan(self):
        ws = _workspace("gen_auto")
        gen = IntegrationGenerator(ws)
        plan = {"integration_id": "auto_api_connector", "integration_type": "rest_api", "capabilities": ["auto_action"]}
        result = gen.generate(plan)
        self.assertEqual(result["status"], "generated")
        written = json.loads((ws / "auto_api_connector" / "manifest.json").read_text())
        self.assertIn("auto_action", written["capabilities"])


# ===========================================================================
# 6. Capability Bridge
# ===========================================================================

class TestCapabilityBridge(unittest.TestCase):

    def _make_contract(self, cap_id: str, integration_id: str = "test_web_connector") -> dict:
        return {
            "id": cap_id,
            "name": cap_id.replace("_", " ").title(),
            "domain": "integraciones",
            "type": "integration",
            "description": f"Capability {cap_id}",
            "inputs": {"x": {"type": "string", "required": True}},
            "outputs": {"status": {"type": "string"}},
            "requirements": {"tools": [], "capabilities": [], "integrations": [integration_id]},
            "strategy": {
                "mode": "sequential",
                "steps": [
                    {"step_id": "noop", "action": "system_get_os_info", "params": {}}
                ],
            },
            "exposure": {"visible_to_user": True, "trigger_phrases": [cap_id]},
            "lifecycle": {"version": "1.0.0", "status": "ready"},
        }

    def test_publish_from_global_contracts(self):
        cap_reg = CapabilityRegistry()
        ws = _workspace("bridge_global")
        global_dir = ws / "global"
        global_dir.mkdir()

        # Write a contract to global dir
        contract = self._make_contract("test_bridge_cap")
        (global_dir / "test_bridge_cap.json").write_text(json.dumps(contract), encoding="utf-8")

        bridge = CapabilityBridge(cap_reg, ws, global_dir)
        manifest = {"id": "test_web_connector", "capabilities": ["test_bridge_cap"]}
        result = bridge.publish("test_web_connector", manifest)

        self.assertEqual(result["total_published"], 1)
        self.assertIn("test_bridge_cap", result["published"])
        self.assertIsNotNone(cap_reg.get("test_bridge_cap"))

    def test_already_registered_not_duplicated(self):
        cap_reg = CapabilityRegistry()
        ws = _workspace("bridge_dup")
        global_dir = ws / "global"
        global_dir.mkdir()

        contract = self._make_contract("already_cap")
        (global_dir / "already_cap.json").write_text(json.dumps(contract), encoding="utf-8")

        # Pre-register
        cap_reg.register(contract, source="pre")

        bridge = CapabilityBridge(cap_reg, ws, global_dir)
        manifest = {"id": "test_web_connector", "capabilities": ["already_cap"]}
        result = bridge.publish("test_web_connector", manifest)

        self.assertEqual(result["total_published"], 0)
        self.assertIn("already_cap", result["already_registered"])

    def test_missing_contract_reported_as_failed(self):
        cap_reg = CapabilityRegistry()
        ws = _workspace("bridge_missing")

        bridge = CapabilityBridge(cap_reg, ws)
        manifest = {"id": "test_web_connector", "capabilities": ["nonexistent_cap"]}
        result = bridge.publish("test_web_connector", manifest)

        self.assertEqual(result["total_published"], 0)
        self.assertEqual(len(result["failed"]), 1)
        self.assertEqual(result["failed"][0]["id"], "nonexistent_cap")

    def test_publish_from_integration_local_dir(self):
        cap_reg = CapabilityRegistry()
        ws = _workspace("bridge_local")
        int_dir = ws / "my_web_connector" / "capabilities"
        int_dir.mkdir(parents=True)

        contract = self._make_contract("local_cap", "my_web_connector")
        (int_dir / "local_cap.json").write_text(json.dumps(contract), encoding="utf-8")

        bridge = CapabilityBridge(cap_reg, ws)
        manifest = {"id": "my_web_connector", "capabilities": ["local_cap"]}
        result = bridge.publish("my_web_connector", manifest)

        self.assertEqual(result["total_published"], 1)
        self.assertIn("local_cap", result["published"])


# ===========================================================================
# 7. Full pipeline: detector → classifier → planner → template → generator → bridge
# ===========================================================================

class TestFullPipeline(unittest.TestCase):

    def test_end_to_end_pipeline(self):
        ws = _workspace("pipeline_e2e")

        # Step 1: Detector records gap
        detector = IntegrationDetector()
        gap = detector.record_gap(
            "post JSON to a REST API endpoint for messaging",
            suggested_capability="send_slack_message",
        )
        self.assertEqual(gap["status"], "open")

        # Step 2: Classifier classifies
        classifier = IntegrationClassifier()
        classification = classifier.classify(gap["intent"])
        self.assertEqual(classification["integration_type"], "rest_api")

        # Step 3: Planner creates plan
        planner = IntegrationPlanner()
        plan = planner.plan(gap, classification)
        self.assertEqual(plan["status"], "proposed")
        self.assertIn("send_slack_message", plan["capabilities"])

        # Step 4: Template Engine renders manifest
        template_engine = TemplateEngine()
        manifest = template_engine.render_manifest(plan)
        self.assertEqual(manifest["type"], "rest_api")
        self.assertEqual(manifest["status"], "not_configured")

        # Step 5: Generator creates structure
        generator = IntegrationGenerator(ws)
        gen_result = generator.generate(plan, manifest)
        self.assertEqual(gen_result["status"], "generated")
        manifest_path = Path(gen_result["manifest_path"])
        self.assertTrue(manifest_path.exists())

        # Write a capability contract into the generated integration
        cap_dir = Path(gen_result["path"]) / "capabilities"
        cap_contract = {
            "id": "send_slack_message",
            "name": "Send Slack Message",
            "domain": "integraciones",
            "type": "integration",
            "description": "Send a message via Slack",
            "inputs": {"message": {"type": "string", "required": True}},
            "outputs": {"status": {"type": "string"}},
            "requirements": {
                "tools": ["network_http_post"],
                "capabilities": [],
                "integrations": [plan["integration_id"]],
            },
            "strategy": {
                "mode": "sequential",
                "steps": [
                    {"step_id": "send", "action": "network_http_post",
                     "params": {"url": "https://slack.example.com", "body": {"text": "{{inputs.message}}"}}}
                ],
            },
            "exposure": {"visible_to_user": True, "trigger_phrases": ["send slack message"]},
            "lifecycle": {"version": "1.0.0", "status": "ready"},
        }
        (cap_dir / "send_slack_message.json").write_text(
            json.dumps(cap_contract), encoding="utf-8",
        )

        # Step 6: Capability Bridge publishes
        cap_reg = CapabilityRegistry()
        bridge = CapabilityBridge(cap_reg, ws)
        pub_result = bridge.publish(plan["integration_id"], manifest)
        self.assertEqual(pub_result["total_published"], 1)
        self.assertIn("send_slack_message", pub_result["published"])

        # Verify capability is now in registry
        self.assertIsNotNone(cap_reg.get("send_slack_message"))

        # Step 7: Detector resolves gap
        resolved = detector.resolve_gap(gap["id"], plan["integration_id"])
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(detector.open_gap_count, 0)


if __name__ == "__main__":
    unittest.main()
