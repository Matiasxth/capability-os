from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMClientError(RuntimeError):
    """Raised when LLM completion fails."""


class LLMAdapter(Protocol):
    def complete(self, system_prompt: str, user_prompt: str, timeout_sec: float) -> str: ...


@dataclass
class OpenAIAPIAdapter:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"

    def complete(self, system_prompt: str, user_prompt: str, timeout_sec: float) -> str:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        return _http_post_json(url, payload, headers, timeout_sec, "openai")


@dataclass
class OllamaAdapter:
    model: str
    base_url: str = "http://127.0.0.1:11434"

    def complete(self, system_prompt: str, user_prompt: str, timeout_sec: float) -> str:
        url = f"{self.base_url.rstrip('/')}/api/generate"
        payload = {
            "model": self.model,
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "stream": False,
            "options": {"temperature": 0},
        }
        headers = {"Content-Type": "application/json"}
        return _http_post_json(url, payload, headers, timeout_sec, "ollama")


class LLMClient:
    """Decoupled LLM wrapper with provider adapters."""

    def __init__(
        self,
        adapter: LLMAdapter | None = None,
        timeout_sec: float = 30.0,
        settings_provider: Callable[[], dict[str, Any]] | None = None,
    ):
        self._explicit_adapter = adapter
        self._settings_provider = settings_provider
        self.timeout_sec = timeout_sec
        self.adapter = adapter or _build_adapter_from_env()

    def configure_from_settings(self, llm_settings: dict[str, Any] | None) -> None:
        adapter = _build_adapter_from_settings(llm_settings, fallback_to_env=True)
        timeout_sec = _resolve_timeout_from_settings(llm_settings, default_timeout_sec=self.timeout_sec)
        self.adapter = adapter
        self.timeout_sec = timeout_sec

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        if self._settings_provider is not None and self._explicit_adapter is None:
            self.configure_from_settings(self._settings_provider())
        if self.adapter is None:
            raise LLMClientError("No LLM provider configured. Set LLM_PROVIDER=openai|ollama.")
        try:
            return self.adapter.complete(system_prompt, user_prompt, self.timeout_sec)
        except Exception as exc:
            if isinstance(exc, LLMClientError):
                raise
            raise LLMClientError(f"LLM completion failed: {exc}") from exc


def _build_adapter_from_env() -> LLMAdapter | None:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        if not api_key:
            raise LLMClientError("OPENAI_API_KEY is required when LLM_PROVIDER=openai.")
        return OpenAIAPIAdapter(api_key=api_key, model=model, base_url=base_url)

    if provider == "ollama":
        model = os.getenv("OLLAMA_MODEL", "llama3.1:8b").strip()
        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
        return OllamaAdapter(model=model, base_url=base_url)

    return None


def _build_adapter_from_settings(
    llm_settings: dict[str, Any] | None,
    *,
    fallback_to_env: bool,
) -> LLMAdapter | None:
    settings = llm_settings if isinstance(llm_settings, dict) else {}
    provider = settings.get("provider")
    if isinstance(provider, str):
        provider = provider.strip().lower()
    else:
        provider = ""

    if provider == "openai":
        api_key = _read_setting(settings, "api_key") or os.getenv("OPENAI_API_KEY", "").strip()
        model = _read_setting(settings, "model") or os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        base_url = _read_setting(settings, "base_url") or os.getenv(
            "OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        ).strip()
        if not api_key:
            raise LLMClientError("OPENAI_API_KEY is required when LLM provider is 'openai'.")
        return OpenAIAPIAdapter(api_key=api_key, model=model, base_url=base_url)

    if provider == "ollama":
        model = _read_setting(settings, "model") or os.getenv("OLLAMA_MODEL", "llama3.1:8b").strip()
        base_url = _read_setting(settings, "base_url") or os.getenv(
            "OLLAMA_BASE_URL",
            "http://127.0.0.1:11434",
        ).strip()
        return OllamaAdapter(model=model, base_url=base_url)

    if fallback_to_env:
        return _build_adapter_from_env()
    return None


def _resolve_timeout_from_settings(
    llm_settings: dict[str, Any] | None,
    *,
    default_timeout_sec: float,
) -> float:
    settings = llm_settings if isinstance(llm_settings, dict) else {}
    timeout_ms = settings.get("timeout_ms")
    if isinstance(timeout_ms, int) and timeout_ms > 0:
        return max(0.1, timeout_ms / 1000)

    env_value = os.getenv("LLM_TIMEOUT_MS", "").strip()
    if env_value.isdigit():
        env_timeout_ms = int(env_value)
        if env_timeout_ms > 0:
            return max(0.1, env_timeout_ms / 1000)
    return max(0.1, float(default_timeout_sec))


def _read_setting(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str):
        return ""
    return value.strip()


def _http_post_json(
    url: str,
    payload: dict,
    headers: dict[str, str],
    timeout_sec: float,
    provider: str,
) -> str:
    # Ensure required headers for all providers (Cloudflare blocks without User-Agent)
    merged = {
        "Content-Type": "application/json",
        "User-Agent": "CapabilityOS/1.0",
        "Accept": "application/json",
    }
    merged.update(headers)
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=merged,
        method="POST",
    )
    try:
        with urlopen(req, timeout=max(1.0, timeout_sec)) as resp:
            body = resp.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMClientError(f"{provider} HTTP error {exc.code}: {detail}") from exc
    except URLError as exc:
        raise LLMClientError(f"{provider} connection error: {exc.reason}") from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise LLMClientError(f"{provider} returned invalid JSON.") from exc

    if provider == "openai":
        choices = parsed.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMClientError("openai response missing choices.")
        message = choices[0].get("message", {})
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMClientError("openai response missing message content.")
        return content

    if provider == "ollama":
        content = parsed.get("response")
        if not isinstance(content, str) or not content.strip():
            raise LLMClientError("ollama response missing 'response' text.")
        return content

    raise LLMClientError(f"Unsupported provider '{provider}'.")
