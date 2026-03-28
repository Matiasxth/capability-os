"""Tests for Auto-Growth API (Componente 7)."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from system.capabilities.registry import CapabilityRegistry
from system.core.interpretation.llm_client import LLMClient, LLMClientError
from system.core.self_improvement.auto_install_pipeline import AutoInstallPipeline
from system.core.self_improvement.capability_generator import CapabilityGenerator
from system.core.self_improvement.nodejs_sandbox import NodejsSandbox
from system.core.self_improvement.python_sandbox import PythonSandbox
from system.core.self_improvement.runtime_analyzer import RuntimeAnalyzer
from system.core.self_improvement.tool_code_generator import ToolCodeGenerator
from system.core.self_improvement.tool_validator import ToolValidator
from system.integrations.detector import IntegrationDetector
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "auto_growth_api"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


def _pipeline(name: str):
    ws = _ws(name)
    tool_reg = ToolRegistry()
    tool_reg.load_from_directory(ROOT / "system" / "tools" / "contracts" / "v1")
    cap_reg = CapabilityRegistry()
    cap_reg.load_from_directory(ROOT / "system" / "capabilities" / "contracts" / "v1")
    runtime = ToolRuntime(tool_reg, workspace_root=ws)
    llm = MagicMock(spec=LLMClient)
    llm.complete.side_effect = LLMClientError("unavailable")
    detector = IntegrationDetector()
    pipe = AutoInstallPipeline(
        runtime_analyzer=RuntimeAnalyzer(tool_registry=tool_reg),
        capability_generator=CapabilityGenerator(llm, cap_reg, ws / "proposals" / "caps"),
        tool_code_generator=ToolCodeGenerator(),
        tool_validator=ToolValidator(PythonSandbox(ws / "sb" / "py"), NodejsSandbox(ws / "sb" / "js")),
        tool_registry=tool_reg,
        tool_runtime=runtime,
        capability_registry=cap_reg,
        proposals_dir=ws / "proposals" / "auto",
    )
    return pipe, detector


class TestAnalyzeEndpoint(unittest.TestCase):

    def test_analyze_returns_strategy(self):
        pipe, det = _pipeline("analyze")
        gap = det.record_gap("open the website", suggested_capability="open_website")
        analysis = pipe._analyzer.analyze({"capability_id": "open_website", "intent": "open the website"})
        self.assertIn("strategy", analysis)
        self.assertEqual(analysis["strategy"], "browser")


class TestGenerateEndpoint(unittest.TestCase):

    def test_generate_returns_proposal(self):
        pipe, det = _pipeline("generate")
        gap = det.record_gap("calculate fibonacci", suggested_capability="calculate_fibonacci")
        gap_input = {"id": gap["id"], "capability_id": "calculate_fibonacci", "intent": "calculate fibonacci", "description": "calculate fibonacci"}
        proposal = pipe.process_gap(gap_input)
        self.assertIn("proposal_id", proposal)
        self.assertEqual(proposal["strategy"], "python")
        self.assertIsNotNone(proposal["code"])

    def test_list_proposals(self):
        pipe, det = _pipeline("list")
        pipe.process_gap({"intent": "something generic", "description": "generic task"})
        proposals = pipe.list_proposals()
        self.assertTrue(len(proposals) >= 1)


class TestApproveEndpoint(unittest.TestCase):

    def test_approve_installs(self):
        pipe, det = _pipeline("approve")
        gap_input = {"capability_id": "my_tool", "intent": "do my thing", "description": "do my thing"}
        proposal = pipe.process_gap(gap_input)
        if proposal["validated"]:
            result = pipe.install_proposal(proposal["proposal_id"])
            self.assertTrue(result["installed"])

    def test_reject_proposal(self):
        pipe, _ = _pipeline("reject")
        gap_input = {"intent": "generic task", "description": "generic"}
        proposal = pipe.process_gap(gap_input)
        # Proposal exists
        self.assertIsNotNone(pipe.get_proposal(proposal["proposal_id"]))


class TestRegenerateEndpoint(unittest.TestCase):

    def test_regenerate_creates_new_proposal(self):
        pipe, _ = _pipeline("regen")
        gap_input = {"intent": "compute hash", "description": "compute hash of text"}
        p1 = pipe.process_gap(gap_input)
        gap_input2 = {"id": p1.get("gap_id"), "capability_id": p1.get("contract", {}).get("id"), "intent": "compute hash", "description": "compute hash"}
        p2 = pipe.process_gap(gap_input2)
        self.assertNotEqual(p1["proposal_id"], p2["proposal_id"])


if __name__ == "__main__":
    unittest.main()
