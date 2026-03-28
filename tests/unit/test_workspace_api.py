"""Tests for Workspace API + Filesystem tool integration (WM-5 + WM-6)."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from system.core.workspace import FileBrowser, PathValidator, WorkspaceContext, WorkspaceRegistry
from system.tools.implementations.phase3_tools import (
    ToolSecurityError,
    filesystem_read_file,
    filesystem_write_file,
    set_path_validator,
)

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "ws_api"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


def _setup(name: str, access: str = "write"):
    ws = _ws(name)
    proj = ws / "project"
    proj.mkdir()
    (proj / "hello.txt").write_text("hello", encoding="utf-8-sig")
    reg = WorkspaceRegistry(ws / "workspaces.json")
    reg.add("Project", str(proj), access=access)
    pv = PathValidator(reg)
    return reg, pv, proj, ws


class TestWorkspaceAPIEndpoints(unittest.TestCase):

    def test_list_workspaces(self):
        reg, _, _, _ = _setup("list")
        self.assertEqual(len(reg.list()), 1)

    def test_add_and_get(self):
        ws = _ws("addget")
        d = ws / "d"
        d.mkdir()
        reg = WorkspaceRegistry(ws / "workspaces.json")
        r = reg.add("D", str(d))
        self.assertIsNotNone(reg.get(r["id"]))

    def test_set_default(self):
        ws = _ws("setdef")
        a, b = ws / "a", ws / "b"
        a.mkdir(); b.mkdir()
        reg = WorkspaceRegistry(ws / "workspaces.json")
        reg.add("A", str(a))
        r2 = reg.add("B", str(b))
        reg.set_default(r2["id"])
        self.assertEqual(reg.get_default()["id"], r2["id"])

    def test_browse(self):
        reg, _, proj, ws = _setup("browse")
        fb = FileBrowser(reg)
        ws_id = reg.list()[0]["id"]
        result = fb.list_directory(ws_id)
        names = {e["name"] for e in result["entries"]}
        self.assertIn("hello.txt", names)

    def test_workspace_context(self):
        reg, _, _, _ = _setup("context")
        ctx = WorkspaceContext(reg)
        result = ctx.get_context()
        self.assertEqual(result["count"], 1)
        self.assertIsNotNone(result["default"])


class TestFilesystemToolIntegration(unittest.TestCase):

    def tearDown(self):
        set_path_validator(None)

    def test_read_allowed_in_write_workspace(self):
        reg, pv, proj, ws = _setup("tool_read")
        set_path_validator(pv)
        try:
            result = filesystem_read_file(
                {"path": str(proj / "hello.txt")},
                {"constraints": {"timeout_ms": 5000, "allowlist": [], "workspace_only": True}},
                proj,
            )
            self.assertEqual(result["content"], "hello")
        finally:
            set_path_validator(None)

    def test_write_blocked_in_read_workspace(self):
        reg, pv, proj, ws = _setup("tool_write_blocked", access="read")
        set_path_validator(pv)
        try:
            with self.assertRaises(ToolSecurityError):
                filesystem_write_file(
                    {"path": str(proj / "new.txt"), "content": "data"},
                    {"constraints": {"timeout_ms": 5000, "allowlist": [], "workspace_only": True}},
                    proj,
                )
        finally:
            set_path_validator(None)

    def test_no_validator_allows_all(self):
        """Without a validator, tools work as before (backward compat)."""
        set_path_validator(None)
        ws = _ws("no_val")
        (ws / "f.txt").write_text("ok", encoding="utf-8-sig")
        result = filesystem_read_file(
            {"path": str(ws / "f.txt")},
            {"constraints": {"timeout_ms": 5000, "allowlist": [], "workspace_only": True}},
            ws,
        )
        self.assertEqual(result["content"], "ok")


if __name__ == "__main__":
    unittest.main()
