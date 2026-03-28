"""Tests for Auto-install Pipeline (Componente 6)."""
from __future__ import annotations

import json
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
from system.tools.registry import ToolRegistry
from system.tools.runtime import ToolRuntime

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "pipeline"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


def _failing_llm() -> LLMClient:
    m = MagicMock(spec=LLMClient)
    m.complete.side_effect = LLMClientError("unavailable")
    return m


def _pipeline(name: str) -> AutoInstallPipeline:
    ws = _ws(name)
    tool_reg = ToolRegistry()
    tool_reg.load_from_directory(ROOT / "system" / "tools" / "contracts" / "v1")
    cap_reg = CapabilityRegistry()
    cap_reg.load_from_directory(ROOT / "system" / "capabilities" / "contracts" / "v1")
    runtime = ToolRuntime(tool_reg, workspace_root=ws)

    llm = _failing_llm()
    return AutoInstallPipeline(
        runtime_analyzer=RuntimeAnalyzer(tool_registry=tool_reg),
        capability_generator=CapabilityGenerator(llm, cap_reg, ws / "proposals" / "caps"),
        tool_code_generator=ToolCodeGenerator(llm_client=None),  # fallback templates
        tool_validator=ToolValidator(
            python_sandbox=PythonSandbox(ws / "sandbox" / "py"),
            nodejs_sandbox=NodejsSandbox(ws / "sandbox" / "js"),
        ),
        tool_registry=tool_reg,
        tool_runtime=runtime,
        capability_registry=cap_reg,
        proposals_dir=ws / "proposals" / "auto",
    )


class TestExistingToolStrategy(unittest.TestCase):

    def test_existing_tool_no_code(self):
        p = _pipeline("existing")
        gap = {"capability_id": "filesystem_read_file", "intent": "read a file"}
        result = p.process_gap(gap)
        self.assertEqual(result["strategy"], "existing_tool")
        self.assertIsNone(result["code"])
        self.assertIsNotNone(result["proposal_id"])


class TestBrowserCLIStrategy(unittest.TestCase):

    def test_browser_strategy(self):
        p = _pipeline("browser")
        gap = {"intent": "open the website and scrape data"}
        result = p.process_gap(gap)
        self.assertEqual(result["strategy"], "browser")
        self.assertIsNone(result["code"])


class TestPythonCodeGeneration(unittest.TestCase):

    def test_python_generates_and_validates(self):
        p = _pipeline("python")
        gap = {"capability_id": "calculate_sum", "intent": "calculate the sum of numbers", "description": "calculate the sum of numbers"}
        result = p.process_gap(gap)
        self.assertEqual(result["strategy"], "python")
        self.assertIsNotNone(result["code"])
        self.assertIn("def execute", result["code"])
        # Fallback template should validate in sandbox
        self.assertTrue(result["validated"])


class TestNotImplementable(unittest.TestCase):

    def test_not_implementable_explains(self):
        p = _pipeline("notimpl")
        gap = {"intent": "make a phone call to the customer"}
        result = p.process_gap(gap)
        self.assertEqual(result["strategy"], "not_implementable")
        self.assertIn("hardware", result["reason"].lower())


class TestInstallProposal(unittest.TestCase):

    def test_install_registers_tool_and_capability(self):
        p = _pipeline("install")
        gap = {"capability_id": "sum_numbers", "intent": "calculate sum", "description": "sum numbers"}
        proposal = p.process_gap(gap)
        self.assertTrue(proposal["validated"])

        install = p.install_proposal(proposal["proposal_id"])
        self.assertTrue(install["installed"])
        self.assertIn("tool_id", install)
        self.assertIn("capability_id", install)

        # Tool should be callable via runtime
        tool_id = install["tool_id"]
        self.assertTrue(p._tool_runtime.has_tool(tool_id))

    def test_install_unvalidated_raises(self):
        p = _pipeline("unvalidated")
        gap = {"intent": "open the website and click button"}
        proposal = p.process_gap(gap)
        # browser strategy → not validated (no code)
        with self.assertRaises(ValueError):
            p.install_proposal(proposal["proposal_id"])


class TestListProposals(unittest.TestCase):

    def test_list_returns_saved(self):
        p = _pipeline("list")
        p.process_gap({"intent": "something generic"})
        proposals = p.list_proposals()
        self.assertTrue(len(proposals) >= 1)


if __name__ == "__main__":
    unittest.main()
