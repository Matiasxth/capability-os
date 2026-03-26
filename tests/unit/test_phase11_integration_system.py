from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from system.core.ui_bridge.api_server import CapabilityOSUIBridgeService

ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tests" / "unit" / ".tmp_runtime" / "phase11_integrations"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


class Phase11IntegrationSystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case_dir = TMP_ROOT / self._testMethodName
        if self.case_dir.exists():
            shutil.rmtree(self.case_dir)
        self.case_dir.mkdir(parents=True, exist_ok=True)

        self.workspace = self.case_dir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.integrations_root = self.case_dir / "integrations" / "installed"
        self.integrations_root.mkdir(parents=True, exist_ok=True)

        self.registry_data_path = self.workspace / "system" / "integrations" / "registry_data.json"

        self._write_manifest(
            "whatsapp_web_connector",
            {
                "id": "whatsapp_web_connector",
                "name": "WhatsApp Web Connector",
                "type": "web_app",
                "status": "ready",
                "capabilities": [
                    "open_whatsapp_web",
                    "wait_for_whatsapp_login",
                    "search_whatsapp_chat",
                    "read_whatsapp_messages",
                    "send_whatsapp_message",
                    "list_whatsapp_visible_chats",
                ],
                "requirements": {"browser": True, "auth": "qr_login_manual"},
                "lifecycle": {"version": "1.0.0"},
            },
        )
        self._write_manifest(
            "broken_web_connector",
            {
                "id": "broken_web_connector",
                "name": "Broken Web Connector",
                "type": "web_app",
                "status": "ready",
                "capabilities": ["read_file"],
                "requirements": {"browser": False},
                "lifecycle": {"version": "1.0.0"},
            },
        )

        self.service = self._new_service()

    def _new_service(self) -> CapabilityOSUIBridgeService:
        return CapabilityOSUIBridgeService(
            workspace_root=self.workspace,
            integrations_root=self.integrations_root,
            integration_registry_data_path=self.registry_data_path,
        )

    def _write_manifest(self, folder_name: str, payload: dict) -> None:
        integration_dir = self.integrations_root / folder_name
        integration_dir.mkdir(parents=True, exist_ok=True)
        (integration_dir / "manifest.json").write_text(json.dumps(payload, indent=2), encoding="utf-8-sig")

    def test_list_integrations(self) -> None:
        response = self.service.handle("GET", "/integrations")
        self.assertEqual(response.status_code, 200)
        integrations = response.payload["integrations"]
        self.assertGreaterEqual(len(integrations), 2)
        by_id = {item["id"]: item for item in integrations}
        self.assertIn("whatsapp_web_connector", by_id)
        self.assertIn("broken_web_connector", by_id)
        self.assertEqual(by_id["whatsapp_web_connector"]["name"], "WhatsApp Web Connector")
        self.assertEqual(by_id["whatsapp_web_connector"]["type"], "web_app")
        self.assertIn(by_id["whatsapp_web_connector"]["status"], {"installed", "validated", "enabled", "disabled", "error"})

    def test_inspect_integration(self) -> None:
        response = self.service.handle("GET", "/integrations/whatsapp_web_connector")
        self.assertEqual(response.status_code, 200)
        integration = response.payload["integration"]
        self.assertEqual(integration["id"], "whatsapp_web_connector")
        self.assertEqual(integration["manifest"]["name"], "WhatsApp Web Connector")
        self.assertIn("open_whatsapp_web", integration["capabilities"])

    def test_validate_integration_valid(self) -> None:
        response = self.service.handle("POST", "/integrations/whatsapp_web_connector/validate", {})
        self.assertEqual(response.status_code, 200)
        payload = response.payload
        self.assertEqual(payload["status"], "success")
        self.assertTrue(payload["validated"])
        self.assertEqual(payload["integration"]["status"], "validated")
        self.assertTrue(payload["integration"]["validated"])
        self.assertIsNotNone(payload["integration"]["last_validated_at"])

    def test_validate_integration_invalid_sets_error(self) -> None:
        response = self.service.handle("POST", "/integrations/broken_web_connector/validate", {})
        self.assertEqual(response.status_code, 200)
        payload = response.payload
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error_code"], "integration_validation_error")
        self.assertEqual(payload["integration"]["status"], "error")
        self.assertFalse(payload["integration"]["validated"])
        errors = payload.get("details", {}).get("errors", [])
        self.assertTrue(any("does not declare integration" in item for item in errors))

    def test_enable_only_if_validated(self) -> None:
        blocked = self.service.handle("POST", "/integrations/whatsapp_web_connector/enable", {})
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.payload["error_code"], "integration_not_validated")

        validated = self.service.handle("POST", "/integrations/whatsapp_web_connector/validate", {})
        self.assertEqual(validated.status_code, 200)
        self.assertEqual(validated.payload["status"], "success")

        enabled = self.service.handle("POST", "/integrations/whatsapp_web_connector/enable", {})
        self.assertEqual(enabled.status_code, 200)
        self.assertEqual(enabled.payload["status"], "success")
        self.assertEqual(enabled.payload["integration"]["status"], "enabled")

    def test_disable_always_works(self) -> None:
        disabled = self.service.handle("POST", "/integrations/whatsapp_web_connector/disable", {})
        self.assertEqual(disabled.status_code, 200)
        self.assertEqual(disabled.payload["status"], "success")
        self.assertEqual(disabled.payload["integration"]["status"], "disabled")

    def test_error_state_is_visible_in_inspect(self) -> None:
        self.service.handle("POST", "/integrations/broken_web_connector/validate", {})
        inspected = self.service.handle("GET", "/integrations/broken_web_connector")
        self.assertEqual(inspected.status_code, 200)
        detail = inspected.payload["integration"]
        self.assertEqual(detail["status"], "error")
        self.assertIsInstance(detail["error"], str)
        self.assertTrue(detail["error"])

    def test_execute_requires_enabled_integration(self) -> None:
        blocked = self.service.handle(
            "POST",
            "/execute",
            {"capability_id": "open_whatsapp_web", "inputs": {}},
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.payload["error_code"], "integration_not_enabled")

        self.service.handle("POST", "/integrations/whatsapp_web_connector/validate", {})
        self.service.handle("POST", "/integrations/whatsapp_web_connector/enable", {})

        def _stub_execute(capability_id: str, inputs: dict):
            if capability_id != "open_whatsapp_web":
                return None
            runtime = {
                "execution_id": "exec_stub",
                "capability_id": "open_whatsapp_web",
                "status": "ready",
                "current_step": None,
                "state": {},
                "logs": [],
                "started_at": "2026-01-01T00:00:00Z",
                "ended_at": "2026-01-01T00:00:01Z",
                "duration_ms": 1000,
                "retry_count": 0,
                "error_code": None,
                "error_message": None,
                "last_completed_step": "open_whatsapp_web",
                "failed_step": None,
                "final_output": {"status": "success", "session_id": "session_stub", "url": "https://web.whatsapp.com/"},
            }
            return {
                "execution_id": "exec_stub",
                "capability_id": "open_whatsapp_web",
                "status": "success",
                "final_output": runtime["final_output"],
                "runtime": runtime,
                "step_outputs": {"open_whatsapp_web": runtime["final_output"]},
            }

        self.service.phase10_whatsapp_executor.execute = _stub_execute  # type: ignore[assignment]
        allowed = self.service.handle(
            "POST",
            "/execute",
            {"capability_id": "open_whatsapp_web", "inputs": {}},
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.payload["status"], "success")

    def test_registry_persistence(self) -> None:
        self.service.handle("POST", "/integrations/whatsapp_web_connector/validate", {})
        self.service.handle("POST", "/integrations/whatsapp_web_connector/enable", {})

        reloaded = self._new_service()
        response = reloaded.handle("GET", "/integrations/whatsapp_web_connector")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload["integration"]["status"], "enabled")
        self.assertTrue(response.payload["integration"]["validated"])


if __name__ == "__main__":
    unittest.main()
