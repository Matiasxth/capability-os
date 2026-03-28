"""Tests for Path Validator (WM-2)."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from system.core.workspace.path_validator import PathValidator
from system.core.workspace.workspace_registry import WorkspaceRegistry

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "path_val"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


def _setup(name: str, access: str = "write", caps: str | list = "*") -> tuple[PathValidator, Path]:
    ws = _ws(name)
    project = ws / "project"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text("x", encoding="utf-8")
    reg = WorkspaceRegistry(ws / "workspaces.json")
    reg.add("Project", str(project), access=access, capabilities=caps)
    return PathValidator(reg), project


class TestAllowed(unittest.TestCase):

    def test_read_in_write_workspace(self):
        pv, proj = _setup("rw")
        result = pv.validate(str(proj / "src" / "main.py"), "read")
        self.assertTrue(result["allowed"])
        self.assertIsNotNone(result["workspace"])

    def test_write_in_write_workspace(self):
        pv, proj = _setup("ww")
        result = pv.validate(str(proj / "src" / "new.py"), "write")
        self.assertTrue(result["allowed"])


class TestDenied(unittest.TestCase):

    def test_path_outside_workspace(self):
        pv, _ = _setup("outside")
        result = pv.validate("/some/random/path", "read")
        self.assertFalse(result["allowed"])
        self.assertIn("outside", result["reason"].lower())

    def test_write_on_read_only(self):
        pv, proj = _setup("readonly", access="read")
        result = pv.validate(str(proj / "file.txt"), "write")
        self.assertFalse(result["allowed"])
        self.assertIn("read-only", result["reason"].lower())

    def test_read_on_read_only_allowed(self):
        pv, proj = _setup("readok", access="read")
        result = pv.validate(str(proj / "file.txt"), "read")
        self.assertTrue(result["allowed"])

    def test_blocked_workspace(self):
        pv, proj = _setup("blocked", access="none")
        result = pv.validate(str(proj / "file.txt"), "read")
        self.assertFalse(result["allowed"])
        self.assertIn("blocked", result["reason"].lower())

    def test_capability_not_permitted(self):
        pv, proj = _setup("caps", caps=["read_file", "list_directory"])
        result = pv.validate(str(proj / "f.txt"), "write", capability_id="delete_file")
        self.assertFalse(result["allowed"])
        self.assertIn("delete_file", result["reason"])

    def test_capability_permitted(self):
        pv, proj = _setup("caps_ok", caps=["read_file", "write_file"])
        result = pv.validate(str(proj / "f.txt"), "write", capability_id="write_file")
        self.assertTrue(result["allowed"])

    def test_wildcard_capabilities(self):
        pv, proj = _setup("wild", caps="*")
        result = pv.validate(str(proj / "f.txt"), "write", capability_id="anything")
        self.assertTrue(result["allowed"])


if __name__ == "__main__":
    unittest.main()
