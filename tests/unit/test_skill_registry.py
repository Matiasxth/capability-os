"""Tests for the Skill Registry."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from system.core.skills.skill_manifest import validate_manifest, SkillManifestError
from system.core.skills.skill_registry import SkillRegistry


class TestSkillManifestValidation(unittest.TestCase):

    def _valid_manifest(self) -> dict[str, Any]:
        return {
            "id": "test-skill",
            "name": "Test Skill",
            "version": "1.0.0",
            "description": "A test skill",
            "capabilities": [{"contract": "capabilities/test.json"}],
            "tools": [{"id": "test_tool", "contract": "tools/test.json"}],
        }

    def test_valid_manifest(self):
        errors = validate_manifest(self._valid_manifest())
        self.assertEqual(errors, [])

    def test_missing_id(self):
        m = self._valid_manifest()
        del m["id"]
        errors = validate_manifest(m)
        self.assertTrue(any("id" in e for e in errors))

    def test_missing_name(self):
        m = self._valid_manifest()
        m["name"] = ""
        errors = validate_manifest(m)
        self.assertTrue(any("name" in e for e in errors))

    def test_bad_version(self):
        m = self._valid_manifest()
        m["version"] = "1"
        errors = validate_manifest(m)
        self.assertTrue(any("semver" in e.lower() or "version" in e.lower() for e in errors))

    def test_bad_capabilities_type(self):
        m = self._valid_manifest()
        m["capabilities"] = "not_a_list"
        errors = validate_manifest(m)
        self.assertTrue(any("list" in e for e in errors))

    def test_missing_contract_in_capability(self):
        m = self._valid_manifest()
        m["capabilities"] = [{"name": "no_contract"}]
        errors = validate_manifest(m)
        self.assertTrue(any("contract" in e for e in errors))

    def test_missing_tool_id(self):
        m = self._valid_manifest()
        m["tools"] = [{"contract": "tools/x.json"}]
        errors = validate_manifest(m)
        self.assertTrue(any("id" in e for e in errors))


class TestSkillRegistry(unittest.TestCase):

    def _create_registry(self) -> tuple[SkillRegistry, Path]:
        tmp = Path(tempfile.mkdtemp())
        return SkillRegistry(skills_dir=tmp), tmp

    def _create_skill_dir(self, base: Path, skill_id: str = "test-skill") -> Path:
        skill_dir = base / skill_id
        skill_dir.mkdir(parents=True)
        manifest = {
            "id": skill_id,
            "name": "Test Skill",
            "version": "1.0.0",
            "description": "Test",
            "capabilities": [],
            "tools": [],
        }
        (skill_dir / "capos-skill.json").write_text(json.dumps(manifest))
        return skill_dir

    def test_install_from_path(self):
        reg, tmp = self._create_registry()
        src = self._create_skill_dir(tmp / "source")
        manifest = reg.install_from_path(src)
        self.assertEqual(manifest["id"], "test-skill")
        self.assertEqual(len(reg.list_installed()), 1)

    def test_install_duplicate_raises(self):
        reg, tmp = self._create_registry()
        src = self._create_skill_dir(tmp / "source")
        reg.install_from_path(src)
        with self.assertRaises(SkillManifestError):
            reg.install_from_path(src)

    def test_install_no_manifest_raises(self):
        reg, tmp = self._create_registry()
        empty_dir = tmp / "empty"
        empty_dir.mkdir()
        with self.assertRaises(SkillManifestError):
            reg.install_from_path(empty_dir)

    def test_uninstall(self):
        reg, tmp = self._create_registry()
        src = self._create_skill_dir(tmp / "source")
        reg.install_from_path(src)
        self.assertTrue(reg.uninstall("test-skill"))
        self.assertEqual(len(reg.list_installed()), 0)

    def test_uninstall_nonexistent(self):
        reg, _ = self._create_registry()
        self.assertFalse(reg.uninstall("nope"))

    def test_get_skill(self):
        reg, tmp = self._create_registry()
        src = self._create_skill_dir(tmp / "source")
        reg.install_from_path(src)
        skill = reg.get_skill("test-skill")
        self.assertIsNotNone(skill)
        self.assertEqual(skill["name"], "Test Skill")

    def test_get_skill_nonexistent(self):
        reg, _ = self._create_registry()
        self.assertIsNone(reg.get_skill("nope"))

    def test_list_installed_empty(self):
        reg, _ = self._create_registry()
        self.assertEqual(reg.list_installed(), [])

    def test_persistence(self):
        reg, tmp = self._create_registry()
        src = self._create_skill_dir(tmp / "source")
        reg.install_from_path(src)
        # Create new registry pointing to same dir
        reg2 = SkillRegistry(skills_dir=reg._skills_dir)
        reg2.load_installed()
        self.assertEqual(len(reg2.list_installed()), 1)

    def test_load_cleans_missing_dirs(self):
        reg, tmp = self._create_registry()
        src = self._create_skill_dir(tmp / "source")
        reg.install_from_path(src)
        # Delete the skill dir but keep state file
        import shutil
        shutil.rmtree(reg._skills_dir / "test-skill")
        reg2 = SkillRegistry(skills_dir=reg._skills_dir)
        reg2.load_installed()
        self.assertEqual(len(reg2.list_installed()), 0)


if __name__ == "__main__":
    unittest.main()
