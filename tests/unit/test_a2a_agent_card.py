"""Tests for A2A Agent Card (Componente 1)."""
from __future__ import annotations

import unittest
from pathlib import Path

from system.capabilities.registry import CapabilityRegistry
from system.core.a2a.agent_card import AgentCardBuilder

ROOT = Path(__file__).resolve().parents[2]


def _registry_with_ready() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.load_from_directory(ROOT / "system" / "capabilities" / "contracts" / "v1")
    return reg


class TestAgentCard(unittest.TestCase):

    def test_card_has_required_fields(self):
        card = AgentCardBuilder(_registry_with_ready()).build()
        for key in ("name", "description", "url", "version", "skills"):
            self.assertIn(key, card, f"Missing field: {key}")
        self.assertEqual(card["name"], "Capability OS")
        self.assertIsInstance(card["skills"], list)

    def test_skills_only_include_ready(self):
        reg = CapabilityRegistry()
        ready = {
            "id": "test_ready", "name": "Ready", "domain": "ejecucion", "type": "base",
            "description": "d", "inputs": {"x": {"type": "string", "required": True}},
            "outputs": {"status": {"type": "string"}},
            "requirements": {"tools": ["execution_run_command"], "capabilities": [], "integrations": []},
            "strategy": {"mode": "sequential", "steps": [{"step_id": "s", "action": "execution_run_command", "params": {}}]},
            "exposure": {"visible_to_user": True, "trigger_phrases": ["test"]},
            "lifecycle": {"version": "1.0.0", "status": "ready"},
        }
        exp = dict(ready, id="test_exp")
        exp["lifecycle"] = {"version": "1.0.0", "status": "experimental"}
        reg.register(ready, source="t")
        reg.register(exp, source="t")
        card = AgentCardBuilder(reg).build()
        ids = {s["id"] for s in card["skills"]}
        self.assertIn("test_ready", ids)
        self.assertNotIn("test_exp", ids)

    def test_skill_has_expected_shape(self):
        card = AgentCardBuilder(_registry_with_ready()).build()
        self.assertTrue(len(card["skills"]) > 0)
        skill = card["skills"][0]
        for key in ("id", "name", "description", "inputModes", "outputModes"):
            self.assertIn(key, skill)

    def test_server_url_configurable(self):
        card = AgentCardBuilder(_registry_with_ready(), server_url="https://my.host:9000").build()
        self.assertEqual(card["url"], "https://my.host:9000")


if __name__ == "__main__":
    unittest.main()
