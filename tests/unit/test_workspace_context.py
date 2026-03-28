"""Tests for Workspace Context (WM-3)."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from system.core.workspace.workspace_context import WorkspaceContext
from system.core.workspace.workspace_registry import WorkspaceRegistry

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "ws_ctx"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


class TestWorkspaceContext(unittest.TestCase):

    def test_empty_registry(self):
        ws = _ws("empty")
        reg = WorkspaceRegistry(ws / "workspaces.json")
        ctx = WorkspaceContext(reg)
        result = ctx.get_context()
        self.assertIsNone(result["default"])
        self.assertEqual(result["all"], [])
        self.assertEqual(result["count"], 0)

    def test_single_workspace(self):
        ws = _ws("single")
        proj = ws / "proj"
        proj.mkdir()
        reg = WorkspaceRegistry(ws / "workspaces.json")
        reg.add("Project", str(proj))
        ctx = WorkspaceContext(reg)
        result = ctx.get_context()
        self.assertIsNotNone(result["default"])
        self.assertEqual(result["default"]["name"], "Project")
        self.assertEqual(result["count"], 1)
        self.assertIn("Project", result["by_name"])

    def test_multiple_workspaces(self):
        ws = _ws("multi")
        a, b = ws / "a", ws / "b"
        a.mkdir(); b.mkdir()
        reg = WorkspaceRegistry(ws / "workspaces.json")
        reg.add("Alpha", str(a))
        reg.add("Beta", str(b))
        ctx = WorkspaceContext(reg)
        result = ctx.get_context()
        self.assertEqual(result["count"], 2)
        self.assertIn("Alpha", result["by_name"])
        self.assertIn("Beta", result["by_name"])

    def test_summary_has_required_fields(self):
        ws = _ws("fields")
        proj = ws / "proj"
        proj.mkdir()
        reg = WorkspaceRegistry(ws / "workspaces.json")
        reg.add("P", str(proj), access="read")
        ctx = WorkspaceContext(reg)
        summary = ctx.get_context()["default"]
        for key in ("id", "name", "path", "access"):
            self.assertIn(key, summary)
        self.assertEqual(summary["access"], "read")

    def test_inactive_excluded(self):
        ws = _ws("inactive")
        a, b = ws / "a", ws / "b"
        a.mkdir(); b.mkdir()
        reg = WorkspaceRegistry(ws / "workspaces.json")
        r = reg.add("Active", str(a))
        r2 = reg.add("Inactive", str(b))
        reg.update(r2["id"], active=False)
        ctx = WorkspaceContext(reg)
        result = ctx.get_context()
        self.assertEqual(result["count"], 1)
        self.assertNotIn("Inactive", result["by_name"])


if __name__ == "__main__":
    unittest.main()
