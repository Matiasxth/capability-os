"""Tests for Workspace Registry (WM-1)."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from system.core.workspace.workspace_registry import WorkspaceRegistry

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "ws_registry"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


class TestAddRemove(unittest.TestCase):

    def test_add_workspace(self):
        ws = _ws("add")
        target = ws / "project"
        target.mkdir()
        reg = WorkspaceRegistry(ws / "workspaces.json")
        result = reg.add("My Project", str(target))
        self.assertIn("id", result)
        self.assertEqual(result["name"], "My Project")
        self.assertEqual(result["access"], "write")
        self.assertEqual(reg.count(), 1)

    def test_duplicate_path_rejected(self):
        ws = _ws("dup")
        target = ws / "project"
        target.mkdir()
        reg = WorkspaceRegistry(ws / "workspaces.json")
        reg.add("First", str(target))
        with self.assertRaises(ValueError):
            reg.add("Second", str(target))

    def test_remove(self):
        ws = _ws("remove")
        t1, t2 = ws / "a", ws / "b"
        t1.mkdir(); t2.mkdir()
        reg = WorkspaceRegistry(ws / "workspaces.json")
        r1 = reg.add("A", str(t1))
        reg.add("B", str(t2))
        self.assertTrue(reg.remove(r1["id"]))
        self.assertEqual(reg.count(), 1)

    def test_cannot_remove_only_workspace(self):
        ws = _ws("only")
        target = ws / "sole"
        target.mkdir()
        reg = WorkspaceRegistry(ws / "workspaces.json")
        r = reg.add("Sole", str(target))
        with self.assertRaises(ValueError):
            reg.remove(r["id"])

    def test_nonexistent_path_rejected(self):
        ws = _ws("nopath")
        reg = WorkspaceRegistry(ws / "workspaces.json")
        with self.assertRaises(FileNotFoundError):
            reg.add("Ghost", str(ws / "ghost"))


class TestDefault(unittest.TestCase):

    def test_first_added_is_default(self):
        ws = _ws("default")
        target = ws / "p"
        target.mkdir()
        reg = WorkspaceRegistry(ws / "workspaces.json")
        r = reg.add("P", str(target))
        self.assertEqual(reg.get_default()["id"], r["id"])

    def test_set_default(self):
        ws = _ws("setdef")
        t1, t2 = ws / "a", ws / "b"
        t1.mkdir(); t2.mkdir()
        reg = WorkspaceRegistry(ws / "workspaces.json")
        reg.add("A", str(t1))
        r2 = reg.add("B", str(t2))
        reg.set_default(r2["id"])
        self.assertEqual(reg.get_default()["id"], r2["id"])

    def test_remove_default_promotes_next(self):
        ws = _ws("promote")
        t1, t2 = ws / "a", ws / "b"
        t1.mkdir(); t2.mkdir()
        reg = WorkspaceRegistry(ws / "workspaces.json")
        r1 = reg.add("A", str(t1))
        r2 = reg.add("B", str(t2))
        reg.remove(r1["id"])
        self.assertIsNotNone(reg.get_default())


class TestQuery(unittest.TestCase):

    def test_get_by_path(self):
        ws = _ws("bypath")
        target = ws / "project"
        (target / "src").mkdir(parents=True)
        reg = WorkspaceRegistry(ws / "workspaces.json")
        reg.add("Project", str(target))
        result = reg.get_by_path(str(target / "src" / "app.py"))
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Project")

    def test_get_by_path_not_found(self):
        ws = _ws("bypath_ne")
        reg = WorkspaceRegistry(ws / "workspaces.json")
        self.assertIsNone(reg.get_by_path("/nonexistent/path"))


class TestPersistence(unittest.TestCase):

    def test_survives_reload(self):
        ws = _ws("persist")
        target = ws / "p"
        target.mkdir()
        reg1 = WorkspaceRegistry(ws / "workspaces.json")
        r = reg1.add("P", str(target), color="#ff0000")
        reg2 = WorkspaceRegistry(ws / "workspaces.json")
        self.assertEqual(reg2.count(), 1)
        self.assertEqual(reg2.get(r["id"])["color"], "#ff0000")


class TestUpdate(unittest.TestCase):

    def test_update_fields(self):
        ws = _ws("update")
        target = ws / "p"
        target.mkdir()
        reg = WorkspaceRegistry(ws / "workspaces.json")
        r = reg.add("P", str(target))
        updated = reg.update(r["id"], name="New Name", access="read")
        self.assertEqual(updated["name"], "New Name")
        self.assertEqual(updated["access"], "read")


if __name__ == "__main__":
    unittest.main()
