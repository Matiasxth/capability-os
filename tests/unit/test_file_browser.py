"""Tests for File Browser (WM-4)."""
from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from system.core.workspace.file_browser import FileBrowser
from system.core.workspace.workspace_registry import WorkspaceRegistry

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tests" / "unit" / ".tmp_runtime" / "file_browser"


def _ws(name: str) -> Path:
    ws = TMP / name
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    return ws


def _setup(name: str) -> tuple[FileBrowser, str, Path]:
    ws = _ws(name)
    proj = ws / "project"
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "main.py").write_text("print('hi')", encoding="utf-8")
    (proj / "src" / "utils.js").write_text("//js", encoding="utf-8")
    (proj / "README.md").write_text("# Readme", encoding="utf-8")
    (proj / ".git").mkdir()
    (proj / "node_modules").mkdir()
    reg = WorkspaceRegistry(ws / "workspaces.json")
    r = reg.add("Project", str(proj))
    fb = FileBrowser(reg)
    return fb, r["id"], proj


class TestListDirectory(unittest.TestCase):

    def test_root_listing(self):
        fb, ws_id, proj = _setup("root")
        result = fb.list_directory(ws_id)
        self.assertEqual(result["path"], ".")
        names = {e["name"] for e in result["entries"]}
        self.assertIn("src", names)
        self.assertIn("README.md", names)

    def test_hidden_dirs_excluded(self):
        fb, ws_id, _ = _setup("hidden")
        result = fb.list_directory(ws_id)
        names = {e["name"] for e in result["entries"]}
        self.assertNotIn(".git", names)
        self.assertNotIn("node_modules", names)

    def test_subdirectory_listing(self):
        fb, ws_id, _ = _setup("subdir")
        result = fb.list_directory(ws_id, "src")
        self.assertEqual(result["path"], "src")
        names = {e["name"] for e in result["entries"]}
        self.assertIn("main.py", names)
        self.assertIn("utils.js", names)

    def test_file_has_extension_and_size(self):
        fb, ws_id, _ = _setup("meta")
        result = fb.list_directory(ws_id, "src")
        py_file = next(e for e in result["entries"] if e["name"] == "main.py")
        self.assertEqual(py_file["type"], "file")
        self.assertEqual(py_file["extension"], ".py")
        self.assertGreater(py_file["size"], 0)

    def test_directories_first(self):
        fb, ws_id, _ = _setup("order")
        result = fb.list_directory(ws_id)
        types = [e["type"] for e in result["entries"]]
        # Directories should come before files
        if "directory" in types and "file" in types:
            last_dir = max(i for i, t in enumerate(types) if t == "directory")
            first_file = min(i for i, t in enumerate(types) if t == "file")
            self.assertLess(last_dir, first_file)

    def test_escape_blocked(self):
        fb, ws_id, _ = _setup("escape")
        with self.assertRaises(PermissionError):
            fb.list_directory(ws_id, "../..")

    def test_unknown_workspace(self):
        fb, _, _ = _setup("unknown")
        with self.assertRaises(KeyError):
            fb.list_directory("ws_nonexistent")

    def test_nonexistent_subdir(self):
        fb, ws_id, _ = _setup("nodir")
        with self.assertRaises(FileNotFoundError):
            fb.list_directory(ws_id, "ghost_dir")


if __name__ == "__main__":
    unittest.main()
