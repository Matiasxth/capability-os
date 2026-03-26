from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from system.core.ui_bridge.api_server import CapabilityOSUIBridgeService

ROOT = Path(__file__).resolve().parents[2]
TMP_ROOT = ROOT / "tests" / "unit" / ".tmp_runtime" / "control_center_backend"
TMP_ROOT.mkdir(parents=True, exist_ok=True)


class _StubLLMClient:
    def __init__(self, *, should_fail: bool = False):
        self.should_fail = should_fail
        self.last_settings = None

    def configure_from_settings(self, settings: dict) -> None:
        self.last_settings = settings

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        if self.should_fail:
            raise RuntimeError("stub llm unavailable")
        return "ok"


class ControlCenterBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case_dir = TMP_ROOT / self._testMethodName
        if self.case_dir.exists():
            shutil.rmtree(self.case_dir)
        self.case_dir.mkdir(parents=True, exist_ok=True)
        self.workspace = self.case_dir / "workspace"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.llm_stub = _StubLLMClient()
        self.service = CapabilityOSUIBridgeService(
            workspace_root=self.workspace,
            llm_client=self.llm_stub,  # type: ignore[arg-type]
        )

    def test_save_and_get_settings_masks_api_key(self) -> None:
        response = self.service.handle("POST", "/settings", {
            "settings": {
                "llm": {
                    "provider": "openai",
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-4o-mini",
                    "api_key": "sk-test-123456",
                    "timeout_ms": 30000,
                },
                "browser": {"auto_start": True},
                "workspace": {
                    "artifacts_path": str((self.workspace / "artifacts").resolve()),
                    "sequences_path": str((self.workspace / "sequences").resolve()),
                },
            }
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload["status"], "success")

        get_response = self.service.handle("GET", "/settings")
        self.assertEqual(get_response.status_code, 200)
        masked = get_response.payload["settings"]["llm"]["api_key"]
        self.assertNotEqual(masked, "sk-test-123456")
        self.assertTrue(masked.endswith("3456"))

        on_disk = self.workspace / "system" / "settings.json"
        self.assertTrue(on_disk.exists())
        parsed = json.loads(on_disk.read_text(encoding="utf-8-sig"))
        self.assertEqual(parsed["llm"]["api_key"], "sk-test-123456")

    def test_settings_validation_rejects_invalid_paths(self) -> None:
        response = self.service.handle("POST", "/settings", {
            "settings": {
                "llm": {
                    "provider": "ollama",
                    "base_url": "http://127.0.0.1:11434",
                    "model": "llama3.1:8b",
                    "api_key": "",
                    "timeout_ms": 30000,
                },
                "browser": {"auto_start": True},
                "workspace": {
                    "artifacts_path": "C:/outside/artifacts",
                    "sequences_path": "C:/outside/sequences",
                },
            }
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.payload["error_code"], "settings_validation_error")
        errors = response.payload.get("details", {}).get("errors", [])
        self.assertTrue(any("outside workspace" in item for item in errors))

    def test_llm_test_endpoint_uses_current_settings(self) -> None:
        save_response = self.service.handle("POST", "/settings", {
            "settings": {
                "llm": {
                    "provider": "ollama",
                    "base_url": "http://127.0.0.1:11434",
                    "model": "llama3.1:8b",
                    "api_key": "",
                    "timeout_ms": 30000,
                },
                "browser": {"auto_start": True},
                "workspace": {
                    "artifacts_path": str((self.workspace / "artifacts").resolve()),
                    "sequences_path": str((self.workspace / "sequences").resolve()),
                },
            }
        })
        self.assertEqual(save_response.status_code, 200)

        response = self.service.handle("POST", "/llm/test", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload["status"], "success")
        self.assertEqual(response.payload["provider"], "ollama")
        self.assertIsInstance(self.llm_stub.last_settings, dict)
        self.assertEqual(self.llm_stub.last_settings.get("model"), "llama3.1:8b")

    def test_health_endpoint_returns_aggregated_status(self) -> None:
        response = self.service.handle("GET", "/health")
        self.assertEqual(response.status_code, 200)
        payload = response.payload
        self.assertIn("status", payload)
        self.assertIn("llm", payload)
        self.assertIn("browser_worker", payload)
        self.assertIn("integrations", payload)
        self.assertIn("uptime_ms", payload)

    def test_browser_restart_endpoint(self) -> None:
        response = self.service.handle("POST", "/browser/restart", {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.payload["status"], "success")
        self.assertIn("browser_worker", response.payload)


if __name__ == "__main__":
    unittest.main()
