from __future__ import annotations

import json
import unittest
from pathlib import Path

from system.shared.schema_validation import SchemaValidationError, load_schema, validate_instance

ROOT = Path(__file__).resolve().parents[2]


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


class SchemaValidationTests(unittest.TestCase):
    def test_capability_schema_accepts_valid_contract(self) -> None:
        schema = load_schema(ROOT / "system/capabilities/contracts/capability_contract.schema.json")
        contract = _load_json(ROOT / "tests/unit/fixtures/capabilities/valid_create_project.json")
        validate_instance(contract, schema, context="valid capability")

    def test_capability_schema_rejects_invalid_contract(self) -> None:
        schema = load_schema(ROOT / "system/capabilities/contracts/capability_contract.schema.json")
        contract = _load_json(ROOT / "tests/unit/fixtures/capabilities/invalid_missing_domain.json")
        with self.assertRaises(SchemaValidationError):
            validate_instance(contract, schema, context="invalid capability")

    def test_tool_schema_accepts_valid_contract(self) -> None:
        schema = load_schema(ROOT / "system/tools/contracts/tool_contract.schema.json")
        contract = _load_json(ROOT / "tests/unit/fixtures/tools/valid_execution_run_command.json")
        validate_instance(contract, schema, context="valid tool")

    def test_tool_schema_rejects_invalid_contract(self) -> None:
        schema = load_schema(ROOT / "system/tools/contracts/tool_contract.schema.json")
        contract = _load_json(ROOT / "tests/unit/fixtures/tools/invalid_missing_category.json")
        with self.assertRaises(SchemaValidationError):
            validate_instance(contract, schema, context="invalid tool")

    def test_integration_manifest_schema_validation(self) -> None:
        schema = load_schema(ROOT / "system/integrations/contracts/integration_manifest.schema.json")

        valid_manifest = {
            "id": "whatsapp_web_connector",
            "name": "WhatsApp Web Connector",
            "type": "web_app",
            "status": "ready",
            "capabilities": ["list_integrations"],
            "requirements": {"browser": True, "auth": "qr_login"},
            "lifecycle": {"version": "1.0.0"},
        }
        validate_instance(valid_manifest, schema, context="valid integration manifest")

        invalid_manifest = {
            "id": "whatsapp-web",
            "status": "ready",
            "capabilities": ["list_integrations"],
            "requirements": {},
            "lifecycle": {"version": "1.0.0"},
        }
        with self.assertRaises(SchemaValidationError):
            validate_instance(invalid_manifest, schema, context="invalid integration manifest")

    def test_whatsapp_manifest_file_is_valid(self) -> None:
        schema = load_schema(ROOT / "system/integrations/contracts/integration_manifest.schema.json")
        manifest = _load_json(
            ROOT / "system/integrations/installed/whatsapp_web_connector/manifest.json"
        )
        validate_instance(manifest, schema, context="whatsapp manifest file")


if __name__ == "__main__":
    unittest.main()

