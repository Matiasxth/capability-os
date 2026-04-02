from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable

from system.core.settings import SettingsService


class HealthService:
    """Aggregates health information for UI/control center consumption."""

    def __init__(
        self,
        *,
        settings_service: SettingsService,
        browser_status_provider: Callable[[], dict[str, Any]],
        integrations_provider: Callable[[], list[dict[str, Any]]],
    ):
        self.settings_service = settings_service
        self.browser_status_provider = browser_status_provider
        self.integrations_provider = integrations_provider
        self.started_at = datetime.now(timezone.utc)

    def get_llm_status(self) -> dict[str, Any]:
        settings = self.settings_service.get_settings(mask_secrets=False)
        llm = settings.get("llm", {})
        provider = llm.get("provider", "unknown")
        api_key = llm.get("api_key", "")
        if not api_key:
            env_keys = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}
            api_key = os.getenv(env_keys.get(provider, ""), "").strip()

        VALID_PROVIDERS = {"openai", "ollama", "anthropic", "gemini", "deepseek"}
        NEEDS_KEY = {"openai", "anthropic", "gemini", "deepseek"}

        issues: list[str] = []
        if provider in NEEDS_KEY and not api_key:
            issues.append(f"{provider} provider requires api_key.")
        if provider not in VALID_PROVIDERS:
            issues.append(f"unsupported llm provider: {provider}.")

        if issues:
            status = "not_configured"
        else:
            status = "ready"

        return {
            "status": status,
            "provider": provider,
            "model": llm.get("model"),
            "base_url": llm.get("base_url"),
            "timeout_ms": llm.get("timeout_ms"),
            "suggest_only": True,
            "issues": issues,
        }

    def get_browser_status(self) -> dict[str, Any]:
        browser = self.browser_status_provider()
        transport = browser.get("transport", {})
        alive = bool(transport.get("alive"))
        failed = bool(transport.get("worker_failed"))
        backend = browser.get("backend", "playwright")
        if alive:
            status = "ready"
        elif failed:
            status = "error"
        elif backend == "playwright":
            status = "available"
        else:
            status = "not_configured"

        payload = dict(browser)
        payload["status"] = status
        return payload

    def get_integrations_status(self) -> dict[str, Any]:
        items = self.integrations_provider()
        enabled = sum(1 for item in items if item.get("status") == "enabled")
        error_count = sum(1 for item in items if item.get("status") == "error")
        return {
            "total": len(items),
            "enabled": enabled,
            "error": error_count,
            "items": items,
        }

    def get_system_health(self) -> dict[str, Any]:
        llm = self.get_llm_status()
        browser = self.get_browser_status()
        integrations = self.get_integrations_status()

        issues: list[str] = []
        if llm["status"] != "ready":
            issues.extend(llm.get("issues", []))
        if browser.get("status") == "error":
            dead_reason = browser.get("transport", {}).get("dead_reason")
            if dead_reason:
                issues.append(f"browser worker error: {dead_reason}")
            else:
                issues.append("browser worker is unavailable.")
        if integrations.get("error", 0) > 0:
            issues.append("one or more integrations are in error state.")

        status = "ready" if not issues else "error"
        now = datetime.now(timezone.utc)
        uptime_ms = int((now - self.started_at).total_seconds() * 1000)
        return {
            "status": status,
            "started_at": self.started_at.isoformat().replace("+00:00", "Z"),
            "uptime_ms": uptime_ms,
            "issues": issues,
            "llm": llm,
            "browser_worker": browser,
            "integrations": integrations,
        }
