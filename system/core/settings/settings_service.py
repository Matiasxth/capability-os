from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


VALID_LLM_PROVIDERS = {"openai", "ollama"}
DEFAULT_TIMEOUT_MS = 30000


class SettingsValidationError(RuntimeError):
    """Raised when settings payload has an invalid structure."""

    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.details = details or []


class SettingsService:
    """Central settings persistence + validation for Capability OS."""

    def __init__(
        self,
        workspace_root: str | Path,
        settings_path: str | Path | None = None,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.settings_path = Path(settings_path).resolve() if settings_path else (
            self.workspace_root / "system" / "settings.json"
        ).resolve()

    def load_settings(self) -> dict[str, Any]:
        raw_payload: dict[str, Any] = {}
        if self.settings_path.exists():
            try:
                parsed = json.loads(self.settings_path.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError as exc:
                raise SettingsValidationError(
                    f"Settings file '{self.settings_path}' contains invalid JSON."
                ) from exc
            if not isinstance(parsed, dict):
                raise SettingsValidationError("Settings root must be a JSON object.")
            raw_payload = parsed

        merged = self._build_merged_payload(raw_payload)
        return self.validate_settings(merged)

    def get_settings(self, *, mask_secrets: bool = True) -> dict[str, Any]:
        settings = self.load_settings()
        if not mask_secrets:
            return settings

        masked = deepcopy(settings)
        api_key = masked.get("llm", {}).get("api_key")
        if isinstance(api_key, str):
            masked["llm"]["api_key"] = _mask_secret(api_key)
        return masked

    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise SettingsValidationError("Settings payload must be a JSON object.")

        current = self.load_settings()
        merged = self._merge_with_current(current, payload)
        validated = self.validate_settings(merged)

        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(validated, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return deepcopy(validated)

    def validate_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        errors: list[str] = []
        normalized = deepcopy(payload)

        llm = normalized.get("llm")
        if not isinstance(llm, dict):
            errors.append("Field 'llm' must be an object.")
            llm = {}
            normalized["llm"] = llm

        provider = llm.get("provider")
        if not isinstance(provider, str) or provider not in VALID_LLM_PROVIDERS:
            errors.append("Field 'llm.provider' must be 'ollama' or 'openai'.")

        base_url = llm.get("base_url")
        if not isinstance(base_url, str) or not base_url.strip():
            errors.append("Field 'llm.base_url' must be a non-empty string.")
        else:
            llm["base_url"] = base_url.strip()

        model = llm.get("model")
        if not isinstance(model, str) or not model.strip():
            errors.append("Field 'llm.model' must be a non-empty string.")
        else:
            llm["model"] = model.strip()

        api_key = llm.get("api_key")
        if not isinstance(api_key, str):
            errors.append("Field 'llm.api_key' must be a string.")
        else:
            llm["api_key"] = api_key.strip()

        timeout_ms = llm.get("timeout_ms")
        if not isinstance(timeout_ms, int) or timeout_ms <= 0:
            errors.append("Field 'llm.timeout_ms' must be a positive integer.")

        browser = normalized.get("browser")
        if not isinstance(browser, dict):
            errors.append("Field 'browser' must be an object.")
            browser = {}
            normalized["browser"] = browser
        auto_start = browser.get("auto_start")
        if not isinstance(auto_start, bool):
            errors.append("Field 'browser.auto_start' must be boolean.")

        workspace = normalized.get("workspace")
        if not isinstance(workspace, dict):
            errors.append("Field 'workspace' must be an object.")
            workspace = {}
            normalized["workspace"] = workspace

        artifacts_path = workspace.get("artifacts_path")
        sequences_path = workspace.get("sequences_path")
        for field_name, value in (
            ("workspace.artifacts_path", artifacts_path),
            ("workspace.sequences_path", sequences_path),
        ):
            if not isinstance(value, str) or not value.strip():
                errors.append(f"Field '{field_name}' must be a non-empty string.")
                continue
            try:
                resolved = self._resolve_workspace_path(value)
                workspace[field_name.split(".")[1]] = str(resolved)
            except SettingsValidationError as exc:
                errors.append(str(exc))

        if errors:
            raise SettingsValidationError("Settings validation failed.", details=errors)
        return normalized

    def _build_merged_payload(self, raw_payload: dict[str, Any]) -> dict[str, Any]:
        defaults = _defaults_from_env(self.workspace_root)
        return self._deep_merge(defaults, raw_payload)

    def _merge_with_current(self, current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged = self._deep_merge(current, incoming)

        current_api_key = current.get("llm", {}).get("api_key")
        incoming_api_key = incoming.get("llm", {}).get("api_key")
        if incoming_api_key is None:
            merged["llm"]["api_key"] = current_api_key
        elif isinstance(incoming_api_key, str):
            trimmed = incoming_api_key.strip()
            if not trimmed or _looks_masked(trimmed):
                merged["llm"]["api_key"] = current_api_key
            else:
                merged["llm"]["api_key"] = trimmed

        return merged

    def _resolve_workspace_path(self, value: str) -> Path:
        raw = Path(value.strip())
        candidate = raw if raw.is_absolute() else (self.workspace_root / raw)
        resolved = candidate.resolve()
        try:
            common = os.path.commonpath([str(self.workspace_root), str(resolved)])
        except ValueError as exc:
            raise SettingsValidationError(
                f"Path '{value}' is outside workspace '{self.workspace_root}'."
            ) from exc
        if Path(common) != self.workspace_root:
            raise SettingsValidationError(
                f"Path '{value}' is outside workspace '{self.workspace_root}'."
            )
        return resolved

    @staticmethod
    def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
        merged = deepcopy(base)
        for key, value in overrides.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = SettingsService._deep_merge(merged[key], value)
            else:
                merged[key] = deepcopy(value)
        return merged


def _defaults_from_env(workspace_root: Path) -> dict[str, Any]:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider not in VALID_LLM_PROVIDERS:
        provider = "ollama"

    if provider == "openai":
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
    else:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
        model = os.getenv("OLLAMA_MODEL", "llama3.1:8b").strip()
        api_key = os.getenv("OLLAMA_API_KEY", "").strip()

    timeout_raw = os.getenv("LLM_TIMEOUT_MS", str(DEFAULT_TIMEOUT_MS)).strip()
    timeout_ms = DEFAULT_TIMEOUT_MS
    if timeout_raw.isdigit():
        timeout_ms = int(timeout_raw)

    return {
        "llm": {
            "provider": provider,
            "base_url": base_url,
            "model": model,
            "api_key": api_key,
            "timeout_ms": timeout_ms if timeout_ms > 0 else DEFAULT_TIMEOUT_MS,
        },
        "browser": {
            "auto_start": True,
        },
        "workspace": {
            "artifacts_path": str((workspace_root / "artifacts").resolve()),
            "sequences_path": str((workspace_root / "sequences").resolve()),
        },
    }


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 4:
        return "*" * len(value)
    return ("*" * (len(value) - 4)) + value[-4:]


def _looks_masked(value: str) -> bool:
    if "*" not in value:
        return False
    if set(value) == {"*"}:
        return True
    return any(char.isalnum() for char in value)
