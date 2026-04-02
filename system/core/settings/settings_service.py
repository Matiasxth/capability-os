from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any


VALID_LLM_PROVIDERS = {"openai", "ollama", "anthropic", "gemini", "deepseek"}
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
        db: Any = None,
    ):
        self.workspace_root = Path(workspace_root).resolve()
        self.settings_path = Path(settings_path).resolve() if settings_path else (
            self.workspace_root / "system" / "settings.json"
        ).resolve()
        self._lock = threading.RLock()
        self._repo: Any = None
        if db is not None:
            try:
                from system.infrastructure.repositories.settings_repo import SettingsRepository
                self._repo = SettingsRepository(db)
            except Exception:
                pass

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
        elif self._repo is not None:
            # JSON file missing — try loading from DB
            try:
                db_settings = self._repo.get_all()
                if db_settings:
                    raw_payload = db_settings
            except Exception:
                pass

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

        with self._lock:
            current = self.load_settings()
            merged = self._merge_with_current(current, payload)
            validated = self.validate_settings(merged)

            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.settings_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(validated, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(self.settings_path)
            # Persist to DB as secondary storage
            if self._repo is not None:
                try:
                    for key, value in validated.items():
                        self._repo.set(key, value)
                except Exception:
                    pass
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
        backend = browser.get("backend")
        if backend is not None and backend not in ("playwright", "cdp"):
            errors.append("Field 'browser.backend' must be 'playwright' or 'cdp'.")
        auto_start = browser.get("auto_start")
        if not isinstance(auto_start, bool):
            errors.append("Field 'browser.auto_start' must be boolean.")
        cdp_port = browser.get("cdp_port")
        if cdp_port is not None and (not isinstance(cdp_port, int) or cdp_port < 0):
            errors.append("Field 'browser.cdp_port' must be a non-negative integer.")
        auto_restart_max_retries = browser.get("auto_restart_max_retries")
        if auto_restart_max_retries is not None and (not isinstance(auto_restart_max_retries, int) or auto_restart_max_retries < 0):
            errors.append("Field 'browser.auto_restart_max_retries' must be a non-negative integer.")

        whatsapp = normalized.get("whatsapp")
        if whatsapp is not None and isinstance(whatsapp, dict):
            wsp_backend = whatsapp.get("backend")
            if wsp_backend is not None and wsp_backend not in ("official", "browser", "baileys"):
                errors.append("Field 'whatsapp.backend' must be 'official', 'browser', or 'baileys'.")
            official = whatsapp.get("official")
            if official is not None and not isinstance(official, dict):
                errors.append("Field 'whatsapp.official' must be an object.")
            allowed = whatsapp.get("allowed_user_ids")
            if allowed is not None and not isinstance(allowed, list):
                errors.append("Field 'whatsapp.allowed_user_ids' must be an array.")

        agent = normalized.get("agent")
        if agent is not None and isinstance(agent, dict):
            agent_enabled = agent.get("enabled")
            if agent_enabled is not None and not isinstance(agent_enabled, bool):
                errors.append("Field 'agent.enabled' must be boolean.")
            max_iter = agent.get("max_iterations")
            if max_iter is not None and (not isinstance(max_iter, int) or max_iter < 1):
                errors.append("Field 'agent.max_iterations' must be a positive integer.")

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

        mcp = normalized.get("mcp")
        if mcp is not None:
            if not isinstance(mcp, dict):
                errors.append("Field 'mcp' must be an object when present.")
            else:
                servers = mcp.get("servers")
                if servers is not None and not isinstance(servers, list):
                    errors.append("Field 'mcp.servers' must be an array.")
                auto_disc = mcp.get("auto_discover_capabilities")
                if auto_disc is not None and not isinstance(auto_disc, bool):
                    errors.append("Field 'mcp.auto_discover_capabilities' must be boolean.")
                srv_timeout = mcp.get("server_timeout_ms")
                if srv_timeout is not None and (not isinstance(srv_timeout, int) or srv_timeout <= 0):
                    errors.append("Field 'mcp.server_timeout_ms' must be a positive integer.")

        a2a = normalized.get("a2a")
        if a2a is not None:
            if not isinstance(a2a, dict):
                errors.append("Field 'a2a' must be an object when present.")
            else:
                if a2a.get("enabled") is not None and not isinstance(a2a["enabled"], bool):
                    errors.append("Field 'a2a.enabled' must be boolean.")
                if a2a.get("server_url") is not None and not isinstance(a2a["server_url"], str):
                    errors.append("Field 'a2a.server_url' must be a string.")
                if a2a.get("known_agents") is not None and not isinstance(a2a["known_agents"], list):
                    errors.append("Field 'a2a.known_agents' must be an array.")

        telegram = normalized.get("telegram")
        if telegram is not None:
            if not isinstance(telegram, dict):
                errors.append("Field 'telegram' must be an object when present.")

        whatsapp = normalized.get("whatsapp")
        if whatsapp is not None:
            if not isinstance(whatsapp, dict):
                errors.append("Field 'whatsapp' must be an object when present.")

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

    _PROVIDER_DEFAULTS: dict[str, tuple[str, str, str, str]] = {
        # (env_base_url, default_base_url, env_model_default, env_key_name)
        "openai": ("OPENAI_BASE_URL", "https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"),
        "ollama": ("OLLAMA_BASE_URL", "http://127.0.0.1:11434", "llama3.1:8b", "OLLAMA_API_KEY"),
        "anthropic": ("ANTHROPIC_BASE_URL", "https://api.anthropic.com", "claude-sonnet-4-20250514", "ANTHROPIC_API_KEY"),
        "gemini": ("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com", "gemini-2.0-flash", "GEMINI_API_KEY"),
        "deepseek": ("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1", "deepseek-chat", "DEEPSEEK_API_KEY"),
    }
    env_url_key, default_url, default_model, env_key_name = _PROVIDER_DEFAULTS.get(provider, _PROVIDER_DEFAULTS["ollama"])
    base_url = os.getenv(env_url_key, default_url).strip()
    model = os.getenv(f"{provider.upper()}_MODEL", default_model).strip()
    api_key = os.getenv(env_key_name, "").strip()

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
            "backend": "playwright",
            "auto_start": True,
            "cdp_port": 0,
            "auto_restart_max_retries": 2,
        },
        "workspace": {
            "artifacts_path": str((workspace_root / "artifacts").resolve()),
            "sequences_path": str((workspace_root / "sequences").resolve()),
        },
        "agent": {
            "enabled": True,
            "max_iterations": 10,
        },
        "voice": {
            "stt_provider": "whisper_api",
            "tts_provider": "web_speech",
            "tts_voice": "nova",
            "tts_speed": 1.0,
            "auto_speak": False,
            "language": "es",
        },
        "project_states": [
            {"name": "Idea", "color": "#a855f7", "icon": "\U0001f4a1"},
            {"name": "En construccion", "color": "#ffaa00", "icon": "\U0001f3d7\ufe0f"},
            {"name": "En progreso", "color": "#3b82f6", "icon": "\U0001f680"},
            {"name": "Completado", "color": "#22c55e", "icon": "\u2705"},
            {"name": "Pausado", "color": "#6b7280", "icon": "\u23f8\ufe0f"},
            {"name": "Archivado", "color": "#475569", "icon": "\U0001f4e6"},
        ],
        "mcp": {
            "servers": [],
            "auto_discover_capabilities": False,
            "server_timeout_ms": 10000,
        },
        "a2a": {
            "enabled": True,
            "server_url": "http://localhost:8000",
            "known_agents": [],
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
