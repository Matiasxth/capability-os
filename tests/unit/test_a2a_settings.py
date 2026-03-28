"""Tests for A2A Settings + API (Componente 4)."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from system.core.a2a import AgentCardBuilder
from system.capabilities.registry import CapabilityRegistry
from system.core.settings.settings_service import SettingsService, SettingsValidationError

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "a2a_settings"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


class TestA2ASettings(unittest.TestCase):

    def test_defaults_include_a2a(self):
        ws = _ws("defaults")
        svc = SettingsService(ws)
        s = svc.load_settings()
        self.assertIn("a2a", s)
        self.assertTrue(s["a2a"]["enabled"])
        self.assertEqual(s["a2a"]["server_url"], "http://localhost:8000")
        self.assertEqual(s["a2a"]["known_agents"], [])

    def test_valid_a2a_settings(self):
        ws = _ws("valid")
        svc = SettingsService(ws)
        s = svc.load_settings()
        s["a2a"]["enabled"] = False
        s["a2a"]["server_url"] = "https://my.host:9000"
        validated = svc.validate_settings(s)
        self.assertFalse(validated["a2a"]["enabled"])

    def test_invalid_enabled_raises(self):
        ws = _ws("bad_enabled")
        svc = SettingsService(ws)
        s = svc.load_settings()
        s["a2a"]["enabled"] = "yes"
        with self.assertRaises(SettingsValidationError):
            svc.validate_settings(s)

    def test_invalid_known_agents_raises(self):
        ws = _ws("bad_agents")
        svc = SettingsService(ws)
        s = svc.load_settings()
        s["a2a"]["known_agents"] = "not_a_list"
        with self.assertRaises(SettingsValidationError):
            svc.validate_settings(s)


class TestAgentCardEndpoint(unittest.TestCase):

    def test_card_from_real_registry(self):
        reg = CapabilityRegistry()
        reg.load_from_directory(ROOT / "system" / "capabilities" / "contracts" / "v1")
        card = AgentCardBuilder(reg, "http://localhost:8000").build()
        self.assertEqual(card["name"], "Capability OS")
        self.assertIn("skills", card)
        self.assertTrue(len(card["skills"]) > 0)
        # All skills should be from ready capabilities
        for skill in card["skills"]:
            contract = reg.get(skill["id"])
            self.assertIsNotNone(contract)
            self.assertEqual(contract["lifecycle"]["status"], "ready")


if __name__ == "__main__":
    unittest.main()
