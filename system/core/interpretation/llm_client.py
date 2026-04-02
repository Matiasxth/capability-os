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

    def complete_with_tools(self, messages: list[dict], tools: list[dict], timeout_sec: float = 30.0) -> dict:
        """Function calling nativo — retorna response completa con tool_calls."""
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "temperature": 0,
            "messages": messages,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        return _http_post_json_raw(url, payload, headers, timeout_sec)


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

    def complete_with_tools(self, messages: list[dict], tools: list[dict], timeout_sec: float = 30.0) -> dict:
        """Ollama tool calling via /api/chat (requires Ollama 0.4+)."""
        url = f"{self.base_url.rstrip('/')}/api/chat"
        ollama_tools = []
        for t in tools:
            ollama_tools.append({
                "type": "function",
                "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("parameters", {})},
            })
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False, "tools": ollama_tools}
        headers = {"Content-Type": "application/json"}
        raw = _http_post_json_raw(url, payload, headers, timeout_sec)
        msg = raw.get("message", {})
        result: dict[str, Any] = {"choices": [{"message": {"role": "assistant", "content": msg.get("content"), "tool_calls": []}}]}
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            result["choices"][0]["message"]["tool_calls"].append({
                "id": f"call_{fn.get('name', 'unknown')}", "type": "function",
                "function": {"name": fn.get("name", ""), "arguments": json.dumps(fn.get("arguments", {}))},
            })
        if not result["choices"][0]["message"]["tool_calls"]:
            del result["choices"][0]["message"]["tool_calls"]
        return result


@dataclass
class AnthropicAdapter:
    """Anthropic Claude API adapter with SDK fallback to raw HTTP."""
    api_key: str
    model: str = "claude-sonnet-4-20250514"
    base_url: str = "https://api.anthropic.com"

    def complete(self, system_prompt: str, user_prompt: str, timeout_sec: float) -> str:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key, base_url=self.base_url, timeout=timeout_sec)
            response = client.messages.create(
                model=self.model, max_tokens=4096, system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text
        except ImportError:
            return self._complete_raw(system_prompt, user_prompt, timeout_sec)
        except Exception as exc:
            raise LLMClientError(f"anthropic error: {exc}") from exc

    def complete_with_tools(self, messages: list[dict], tools: list[dict], timeout_sec: float = 30.0) -> dict:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.api_key, base_url=self.base_url, timeout=timeout_sec)
            anthropic_tools = [{"name": t["name"], "description": t.get("description", ""), "input_schema": t.get("parameters", {})} for t in tools]
            response = client.messages.create(model=self.model, max_tokens=4096, messages=messages, tools=anthropic_tools)
            result: dict[str, Any] = {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": []}}]}
            for block in response.content:
                if block.type == "text":
                    result["choices"][0]["message"]["content"] = block.text
                elif block.type == "tool_use":
                    result["choices"][0]["message"]["tool_calls"].append({
                        "id": block.id, "type": "function",
                        "function": {"name": block.name, "arguments": json.dumps(block.input)},
                    })
            if not result["choices"][0]["message"]["tool_calls"]:
                del result["choices"][0]["message"]["tool_calls"]
            return result
        except ImportError:
            raise LLMClientError("anthropic package not installed. Run: pip install anthropic")

    def _complete_raw(self, system_prompt: str, user_prompt: str, timeout_sec: float) -> str:
        url = f"{self.base_url.rstrip('/')}/v1/messages"
        payload = {"model": self.model, "max_tokens": 4096, "system": system_prompt, "messages": [{"role": "user", "content": user_prompt}]}
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}
        raw = _http_post_json_raw(url, payload, headers, timeout_sec)
        content = raw.get("content", [])
        if content and isinstance(content, list):
            return content[0].get("text", "")
        raise LLMClientError("anthropic response missing content.")


@dataclass
class GeminiAdapter:
    """Google Gemini API adapter."""
    api_key: str
    model: str = "gemini-2.0-flash"
    base_url: str = "https://generativelanguage.googleapis.com"

    def complete(self, system_prompt: str, user_prompt: str, timeout_sec: float) -> str:
        url = f"{self.base_url.rstrip('/')}/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {"contents": [{"parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}], "generationConfig": {"temperature": 0}}
        headers = {"Content-Type": "application/json"}
        raw = _http_post_json_raw(url, payload, headers, timeout_sec)
        candidates = raw.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "")
        raise LLMClientError("gemini response missing content.")

    def complete_with_tools(self, messages: list[dict], tools: list[dict], timeout_sec: float = 30.0) -> dict:
        """Gemini function calling via generateContent API."""
        url = f"{self.base_url.rstrip('/')}/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        gemini_tools = []
        for t in tools:
            gemini_tools.append({"name": t["name"], "description": t.get("description", ""), "parameters": t.get("parameters", {})})
        contents = []
        for m in messages:
            role = "model" if m.get("role") == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
        payload: dict[str, Any] = {
            "contents": contents,
            "tools": [{"function_declarations": gemini_tools}],
            "generationConfig": {"temperature": 0},
        }
        headers = {"Content-Type": "application/json"}
        raw = _http_post_json_raw(url, payload, headers, timeout_sec)
        candidates = raw.get("candidates", [])
        result: dict[str, Any] = {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": []}}]}
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            for part in parts:
                if "text" in part:
                    result["choices"][0]["message"]["content"] = part["text"]
                elif "functionCall" in part:
                    fc = part["functionCall"]
                    result["choices"][0]["message"]["tool_calls"].append({
                        "id": f"call_{fc.get('name', 'unknown')}", "type": "function",
                        "function": {"name": fc.get("name", ""), "arguments": json.dumps(fc.get("args", {}))},
                    })
        if not result["choices"][0]["message"]["tool_calls"]:
            del result["choices"][0]["message"]["tool_calls"]
        return result


@dataclass
class DeepSeekAdapter:
    """DeepSeek API adapter (OpenAI-compatible format)."""
    api_key: str
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com/v1"

    def complete(self, system_prompt: str, user_prompt: str, timeout_sec: float) -> str:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload = {"model": self.model, "temperature": 0, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        return _http_post_json(url, payload, headers, timeout_sec, "openai")

    def complete_with_tools(self, messages: list[dict], tools: list[dict], timeout_sec: float = 30.0) -> dict:
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        payload: dict[str, Any] = {"model": self.model, "temperature": 0, "messages": messages}
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        return _http_post_json_raw(url, payload, headers, timeout_sec)


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

    if provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514").strip()
        if not api_key:
            raise LLMClientError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic.")
        return AnthropicAdapter(api_key=api_key, model=model)

    if provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
        if not api_key:
            raise LLMClientError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini.")
        return GeminiAdapter(api_key=api_key, model=model)

    if provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
        if not api_key:
            raise LLMClientError("DEEPSEEK_API_KEY is required when LLM_PROVIDER=deepseek.")
        return DeepSeekAdapter(api_key=api_key, model=model)

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
        base_url = _read_setting(settings, "base_url") or os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip()
        return OllamaAdapter(model=model, base_url=base_url)

    if provider == "anthropic":
        api_key = _read_setting(settings, "api_key") or os.getenv("ANTHROPIC_API_KEY", "").strip()
        model = _read_setting(settings, "model") or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514").strip()
        base_url = _read_setting(settings, "base_url") or "https://api.anthropic.com"
        if not api_key:
            raise LLMClientError("ANTHROPIC_API_KEY is required when LLM provider is 'anthropic'.")
        return AnthropicAdapter(api_key=api_key, model=model, base_url=base_url)

    if provider == "gemini":
        api_key = _read_setting(settings, "api_key") or os.getenv("GEMINI_API_KEY", "").strip()
        model = _read_setting(settings, "model") or os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
        if not api_key:
            raise LLMClientError("GEMINI_API_KEY is required when LLM provider is 'gemini'.")
        return GeminiAdapter(api_key=api_key, model=model)

    if provider == "deepseek":
        api_key = _read_setting(settings, "api_key") or os.getenv("DEEPSEEK_API_KEY", "").strip()
        model = _read_setting(settings, "model") or os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
        base_url = _read_setting(settings, "base_url") or "https://api.deepseek.com/v1"
        if not api_key:
            raise LLMClientError("DEEPSEEK_API_KEY is required when LLM provider is 'deepseek'.")
        return DeepSeekAdapter(api_key=api_key, model=model, base_url=base_url)

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


def _get_pool():
    """Get the LLM connection pool (lazy import to avoid circular deps)."""
    try:
        from system.infrastructure.llm_pool import get_llm_pool
        return get_llm_pool()
    except Exception:
        return None


def _http_post_json_raw(
    url: str,
    payload: dict,
    headers: dict[str, str],
    timeout_sec: float,
) -> dict:
    """POST JSON and return parsed response dict (not just text content)."""
    pool = _get_pool()
    if pool is not None:
        try:
            return pool.post_json(url, payload, headers, timeout_sec)
        except Exception as exc:
            raise LLMClientError(f"HTTP error: {exc}") from exc

    merged = {
        "Content-Type": "application/json",
        "User-Agent": "CapabilityOS/1.0",
        "Accept": "application/json",
    }
    merged.update(headers)
    req = Request(url, data=json.dumps(payload).encode("utf-8"), headers=merged, method="POST")
    try:
        with urlopen(req, timeout=max(1.0, timeout_sec)) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LLMClientError(f"HTTP error {exc.code}: {detail}") from exc
    except URLError as exc:
        raise LLMClientError(f"Connection error: {exc.reason}") from exc


def _http_post_json(
    url: str,
    payload: dict,
    headers: dict[str, str],
    timeout_sec: float,
    provider: str,
) -> str:
    pool = _get_pool()
    if pool is not None:
        try:
            parsed = pool.post_json(url, payload, headers, timeout_sec)
        except Exception as exc:
            raise LLMClientError(f"{provider} request failed: {exc}") from exc
    else:
        # Fallback: raw urllib
        merged = {
            "Content-Type": "application/json",
            "User-Agent": "CapabilityOS/1.0",
            "Accept": "application/json",
        }
        merged.update(headers)
        req = Request(url, data=json.dumps(payload).encode("utf-8"), headers=merged, method="POST")
        try:
            with urlopen(req, timeout=max(1.0, timeout_sec)) as resp:
                raw = resp.read()
                try:
                    body = raw.decode("utf-8")
                except UnicodeDecodeError:
                    body = raw.decode("latin-1").encode("latin-1").decode("utf-8", errors="replace")
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

    if provider == "anthropic":
        content_list = parsed.get("content", [])
        if not isinstance(content_list, list) or not content_list:
            raise LLMClientError("anthropic response missing content.")
        text = content_list[0].get("text", "")
        if not text:
            raise LLMClientError("anthropic response missing text content.")
        return text

    if provider == "gemini":
        candidates = parsed.get("candidates", [])
        if not isinstance(candidates, list) or not candidates:
            raise LLMClientError("gemini response missing candidates.")
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise LLMClientError("gemini response missing content parts.")
        return parts[0].get("text", "")

    raise LLMClientError(f"Unsupported provider '{provider}'.")


def _extract_stream_content(data: dict, provider: str) -> str | None:
    """Extract text content from a streaming chunk for the given provider."""
    if provider == "openai":
        choices = data.get("choices", [])
        if choices:
            delta = choices[0].get("delta", {})
            return delta.get("content")
        return None

    if provider == "anthropic":
        if data.get("type") == "content_block_delta":
            delta = data.get("delta", {})
            if delta.get("type") == "text_delta":
                return delta.get("text")
        return None

    if provider == "gemini":
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text")
        return None

    return None
