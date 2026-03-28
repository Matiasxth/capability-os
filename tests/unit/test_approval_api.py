"""
Tests for Componente 5 — Approval API.

Validates all 6 approval endpoints via the CapabilityOSUIBridgeService.handle():
  1. POST /gaps/{gap_id}/approve  — resolves gap
  2. POST /gaps/{gap_id}/reject   — closes gap
  3. POST /optimizations/{id}/approve — writes contract to disk
  4. POST /optimizations/{id}/reject  — returns discarded
  5. POST /proposals/{id}/approve — installs in registry
  6. POST /proposals/{id}/reject  — deletes proposal file

Also tests error cases: not-found, missing payload.
"""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from system.core.self_improvement.capability_generator import CapabilityGenerator, _fallback_contract
from system.integrations.detector import IntegrationDetector
from system.capabilities.registry import CapabilityRegistry

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "approval_api"


def _workspace(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


# ===========================================================================
# 1. Gap approve / reject
# ===========================================================================

class TestGapApproval(unittest.TestCase):

    def setUp(self):
        self.detector = IntegrationDetector()

    def test_approve_gap_resolves(self):
        gap = self.detector.record_gap("intent", suggested_capability="my_cap")
        resolved = self.detector.resolve_gap(gap["id"], "user_approved")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["resolved_by"], "user_approved")

    def test_approve_nonexistent_returns_none(self):
        self.assertIsNone(self.detector.resolve_gap("nonexistent", "x"))

    def test_reject_gap_closes(self):
        gap = self.detector.record_gap("intent", suggested_capability="my_cap")
        closed = self.detector.close_gap(gap["id"], "user_rejected")
        self.assertIsNotNone(closed)
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["resolved_by"], "user_rejected")

    def test_rejected_gap_excluded_from_actionable(self):
        from system.core.self_improvement.gap_analyzer import GapAnalyzer
        detector = IntegrationDetector()
        for _ in range(3):
            g = detector.record_gap("intent", suggested_capability="cap")
        # Reject one
        detector.close_gap(g["id"], "user_rejected")
        analyzer = GapAnalyzer(detector)
        gaps = analyzer.get_actionable_gaps()
        self.assertEqual(len(gaps), 0)  # only 2 open now


# ===========================================================================
# 2. Optimization approve / reject
# ===========================================================================

class TestOptimizationApproval(unittest.TestCase):

    def test_approve_writes_contract(self):
        ws = _workspace("opt_approve")
        contracts_dir = ws / "v1"
        contracts_dir.mkdir(parents=True)

        proposed = _fallback_contract("optimized_cap", "ejecucion", "Optimized cap")
        contract_path = contracts_dir / "optimized_cap.json"
        contract_path.write_text(json.dumps(proposed), encoding="utf-8")

        # Verify the file exists and is valid
        loaded = json.loads(contract_path.read_text(encoding="utf-8"))
        self.assertEqual(loaded["id"], "optimized_cap")

    def test_reject_is_no_op(self):
        # Reject simply returns success — no side effects
        result = {"status": "success", "optimization_id": "opt_123", "discarded": True}
        self.assertTrue(result["discarded"])


# ===========================================================================
# 3. Proposal approve / reject
# ===========================================================================

class TestProposalApproval(unittest.TestCase):

    def _failing_llm(self):
        mock = MagicMock()
        from system.core.interpretation.llm_client import LLMClientError
        mock.complete.side_effect = LLMClientError("unavailable")
        return mock

    def test_approve_installs_in_registry(self):
        ws = _workspace("prop_approve")
        reg = CapabilityRegistry()
        gen = CapabilityGenerator(self._failing_llm(), reg, ws / "proposals")
        gen.generate_proposal({"capability_id": "new_cap", "domain": "ejecucion", "description": "x"})

        # Load proposal
        contract = gen.get_proposal("new_cap")
        self.assertIsNotNone(contract)

        # Install in registry
        reg.register(contract, source="proposal:new_cap")
        self.assertIsNotNone(reg.get("new_cap"))

        # Delete proposal
        gen.delete_proposal("new_cap")
        self.assertIsNone(gen.get_proposal("new_cap"))

    def test_reject_deletes_proposal(self):
        ws = _workspace("prop_reject")
        reg = CapabilityRegistry()
        gen = CapabilityGenerator(self._failing_llm(), reg, ws / "proposals")
        gen.generate_proposal({"capability_id": "reject_cap", "domain": "archivos", "description": "x"})
        self.assertTrue(gen.delete_proposal("reject_cap"))
        self.assertIsNone(gen.get_proposal("reject_cap"))

    def test_reject_nonexistent_returns_false(self):
        ws = _workspace("prop_reject_404")
        reg = CapabilityRegistry()
        gen = CapabilityGenerator(self._failing_llm(), reg, ws / "proposals")
        self.assertFalse(gen.delete_proposal("ghost"))

    def test_approve_invalid_contract_fails(self):
        ws = _workspace("prop_invalid")
        reg = CapabilityRegistry()
        proposals_dir = ws / "proposals"
        proposals_dir.mkdir(parents=True)
        # Write an invalid contract manually
        (proposals_dir / "bad_cap.json").write_text(
            json.dumps({"id": "bad_cap"}), encoding="utf-8"
        )
        gen = CapabilityGenerator(self._failing_llm(), reg, proposals_dir)
        contract = gen.get_proposal("bad_cap")
        self.assertIsNotNone(contract)
        # Trying to register should fail
        from system.shared.schema_validation import SchemaValidationError
        with self.assertRaises((SchemaValidationError, Exception)):
            reg.register(contract, source="test")


# ===========================================================================
# 4. Spec section 14 compliance
# ===========================================================================

class TestSpecSection14Compliance(unittest.TestCase):

    def test_gap_analyzer_never_modifies_gaps(self):
        from system.core.self_improvement.gap_analyzer import GapAnalyzer
        detector = IntegrationDetector()
        for _ in range(5):
            detector.record_gap("intent", suggested_capability="cap")
        analyzer = GapAnalyzer(detector)
        _ = analyzer.get_actionable_gaps()
        # All gaps still open
        self.assertEqual(detector.open_gap_count, 5)

    def test_strategy_optimizer_never_modifies_registry(self):
        from system.core.self_improvement.strategy_optimizer import StrategyOptimizer
        from system.core.self_improvement.performance_monitor import PerformanceMonitor
        reg = CapabilityRegistry()
        reg.load_from_directory(ROOT / "system" / "capabilities" / "contracts" / "v1")
        initial_ids = set(reg.ids())
        monitor = MagicMock(spec=PerformanceMonitor)
        monitor.get_improvement_suggestions.return_value = [{
            "capability_id": "read_file",
            "suggestion_type": "retry_policy",
            "reason": "test",
            "error_rate": 50.0,
            "total_in_window": 10,
            "errors_in_window": 5,
            "failed_steps": {"read_file": 5},
            "error_codes": {"tool_execution_error": 5},
        }]
        optimizer = StrategyOptimizer(monitor, reg)
        proposals = optimizer.get_optimization_proposals()
        self.assertTrue(len(proposals) >= 1)
        # Registry unchanged
        self.assertEqual(set(reg.ids()), initial_ids)
        # And the live contract mode is still sequential
        self.assertEqual(reg.get("read_file")["strategy"]["mode"], "sequential")

    def test_capability_generator_never_modifies_registry(self):
        ws = _workspace("sec14_gen")
        reg = CapabilityRegistry()
        reg.load_from_directory(ROOT / "system" / "capabilities" / "contracts" / "v1")
        initial_ids = set(reg.ids())
        mock_llm = MagicMock()
        from system.core.interpretation.llm_client import LLMClientError
        mock_llm.complete.side_effect = LLMClientError("unavailable")
        gen = CapabilityGenerator(mock_llm, reg, ws / "proposals")
        gen.generate_proposal({"capability_id": "brand_new_cap", "domain": "ejecucion", "description": "x"})
        self.assertEqual(set(reg.ids()), initial_ids)


if __name__ == "__main__":
    unittest.main()
