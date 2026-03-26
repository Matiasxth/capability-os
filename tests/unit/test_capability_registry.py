from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from system.capabilities.registry import CapabilityRegistry
from system.shared.schema_validation import DuplicateIdError, SchemaValidationError

ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tests" / "unit" / ".tmp_runtime" / "capabilities"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _prepare_case_dir(case_name: str) -> Path:
    case_dir = TMP_ROOT / case_name
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir


class CapabilityRegistryTests(unittest.TestCase):
    def test_capability_registry_loads_valid_contracts(self) -> None:
        contract = _load_json(ROOT / "tests/unit/fixtures/capabilities/valid_create_project.json")
        case_dir = _prepare_case_dir("loads_valid")
        (case_dir / "create_project.json").write_text(json.dumps(contract, indent=2), encoding="utf-8-sig")

        registry = CapabilityRegistry()
        registry.load_from_directory(case_dir)

        self.assertEqual(len(registry), 1)
        self.assertIsNotNone(registry.get("create_project"))
        self.assertEqual(registry.ids(), ["create_project"])

    def test_capability_registry_rejects_invalid_contracts(self) -> None:
        contract = _load_json(ROOT / "tests/unit/fixtures/capabilities/invalid_missing_domain.json")
        case_dir = _prepare_case_dir("rejects_invalid")
        (case_dir / "invalid.json").write_text(json.dumps(contract, indent=2), encoding="utf-8-sig")

        registry = CapabilityRegistry()
        with self.assertRaises(SchemaValidationError):
            registry.load_from_directory(case_dir)

    def test_capability_registry_detects_duplicate_ids(self) -> None:
        contract = _load_json(ROOT / "tests/unit/fixtures/capabilities/valid_create_project.json")
        case_dir = _prepare_case_dir("detects_duplicates")
        (case_dir / "a.json").write_text(json.dumps(contract, indent=2), encoding="utf-8-sig")
        (case_dir / "b.json").write_text(json.dumps(contract, indent=2), encoding="utf-8-sig")

        registry = CapabilityRegistry()
        with self.assertRaises(DuplicateIdError):
            registry.load_from_directory(case_dir)

    def test_capability_registry_rejects_implicit_strategy_variables(self) -> None:
        contract = _load_json(ROOT / "tests/unit/fixtures/capabilities/valid_create_project.json")
        contract["strategy"]["steps"][0]["params"]["command"] = "npm create vite@latest {{project_name}}"
        case_dir = _prepare_case_dir("rejects_implicit_vars")
        (case_dir / "invalid_var.json").write_text(json.dumps(contract, indent=2), encoding="utf-8-sig")

        registry = CapabilityRegistry()
        with self.assertRaises(SchemaValidationError):
            registry.load_from_directory(case_dir)


if __name__ == "__main__":
    unittest.main()
