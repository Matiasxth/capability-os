"""Multi-provider tool-use LLM adapter.

Wraps the existing LLMClient adapters to support tool calling.
Supports: OpenAI/DeepSeek (function calling), Anthropic (tool_use),
Ollama/Gemini (text-based fallback with JSON parsing).
"""
from __future__ import annotations

import json
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


class LLMRateLimiter:
    """Sliding window rate limiter for LLM API calls."""

    def __init__(self, max_rpm: int = 30) -> None:
        self._max_rpm = max_rpm
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()

    def check(self) -> tuple[bool, float]:
        """Returns (allowed, wait_seconds). If not allowed, wait_seconds > 0."""
        now = time.monotonic()
        with self._lock:
            # Remove timestamps older than 60s
            while self._timestamps and now - self._timestamps[0] > 60:
                self._timestamps.popleft()
            if len(self._timestamps) >= self._max_rpm:
                wait = 60 - (now - self._timestamps[0])
                return False, max(0.1, wait)
            self._timestamps.append(now)
            return True, 0

    def configure(self, max_rpm: int) -> None:
        with self._lock:
            self._max_rpm = max(1, max_rpm)


@dataclass
class ToolCall:
    tool_id: str
    params: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""


@dataclass
class AgentResponse:
    text: str | None = None
    tool_calls: list[ToolCall] | None = None
    stop_reason: str = "end_turn"


def build_tool_definitions(tool_registry: Any) -> list[dict[str, Any]]:
    """Convert registered tool contracts into tool definitions for the LLM."""
    definitions = []
    # Support both list_all() and list_ids() patterns
    all_contracts = []
    if hasattr(tool_registry, "list_all"):
        all_contracts = tool_registry.list_all()
    elif hasattr(tool_registry, "list_ids"):
        all_contracts = [tool_registry.get(tid) for tid in tool_registry.list_ids()]

    for contract in all_contracts:
        if contract is None:
            continue
        tool_id = contract.get("id", contract.get("name", ""))
        if not tool_id:
            continue
        raw_inputs = contract.get("inputs", {})
        properties = {}
        required = []
        # inputs is a dict: {"param_name": {"type": "string", "required": true, "description": "..."}}
        if isinstance(raw_inputs, dict):
            for name, info in raw_inputs.items():
                if not isinstance(info, dict):
                    continue
                prop: dict[str, Any] = {
                    "type": _map_type(info.get("type", "string")),
                    "description": info.get("description", ""),
                }
                properties[name] = prop
                if info.get("required", False):
                    required.append(name)

        definitions.append({
            "name": tool_id,
            "description": contract.get("description", tool_id)[:200],
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        })
    return definitions


def _map_type(t: str) -> str:
    mapping = {"string": "string", "integer": "integer", "number": "number",
               "boolean": "boolean", "object": "object", "array": "array"}
    return mapping.get(t, "string")


class ToolUseAdapter:
    """Calls the LLM with tool definitions and parses tool_calls from the response."""

    def __init__(self, llm_client: Any, max_rpm: int = 30) -> None:
        self._client = llm_client
        self._rate_limiter = LLMRateLimiter(max_rpm=max_rpm)

    def run_agent_turn(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system_prompt: str,
    ) -> AgentResponse:
        """Send conversation + tools to LLM, return text and/or tool_calls."""
        provider = self._detect_provider()

        # Try native function calling first (uses adapter's own HTTP method which bypasses Cloudflare)
        adapter = getattr(self._client, "adapter", None)
        if adapter and hasattr(adapter, "complete_with_tools"):
            try:
                return self._native_turn(adapter, messages, tools, system_prompt)
            except Exception:
                pass  # Fall through to text mode

        # Fallback: text-based tool calling (works with all providers)
        return self._text_turn(messages, tools, system_prompt)

    def _detect_provider(self) -> str:
        adapter = getattr(self._client, "adapter", None) or getattr(self._client, "_explicit_adapter", None)
        if adapter is None:
            return "unknown"
        cls_name = type(adapter).__name__.lower()
        if "openai" in cls_name:
            return "openai"
        if "anthropic" in cls_name:
            return "anthropic"
        if "gemini" in cls_name:
            return "gemini"
        if "deepseek" in cls_name:
            return "deepseek"
        if "ollama" in cls_name:
            return "ollama"
        return "unknown"

    # ------------------------------------------------------------------
    # OpenAI / DeepSeek (function calling)
    # ------------------------------------------------------------------

    def _openai_turn(
        self, messages: list[dict], tools: list[dict], system_prompt: str,
    ) -> AgentResponse:
        adapter = getattr(self._client, "adapter", None)
        if adapter is None:
            return self._text_turn(messages, tools, system_prompt)

        # Build OpenAI-format messages
        oai_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            role = m.get("role", "user")
            if role == "tool_result":
                oai_messages.append({
                    "role": "tool",
                    "tool_call_id": m.get("tool_call_id", ""),
                    "content": json.dumps(m.get("content", {}), ensure_ascii=False),
                })
            else:
                oai_messages.append({"role": role, "content": m.get("content", "")})

        # Build function definitions
        oai_tools = []
        for t in tools:
            oai_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("parameters", {}),
                },
            })

        try:
            import urllib.request
            api_key = getattr(adapter, "api_key", "") or ""
            base_url = (getattr(adapter, "base_url", "") or "https://api.openai.com/v1").rstrip("/")
            model = getattr(adapter, "model", "gpt-4o-mini") or "gpt-4o-mini"

            body = json.dumps({
                "model": model,
                "messages": oai_messages,
                "tools": oai_tools if oai_tools else None,
            }, ensure_ascii=False).encode()

            req = urllib.request.Request(
                f"{base_url}/chat/completions",
                data=body,
                method="POST",
            )
            req.add_header("Authorization", f"Bearer {api_key}")
            req.add_header("Content-Type", "application/json")

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())

            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})

            raw_tool_calls = msg.get("tool_calls")
            if raw_tool_calls:
                calls = []
                for tc in raw_tool_calls:
                    fn = tc.get("function", {})
                    try:
                        params = json.loads(fn.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        params = {}
                    calls.append(ToolCall(
                        tool_id=fn.get("name", ""),
                        params=params,
                        call_id=tc.get("id", ""),
                    ))
                return AgentResponse(
                    text=msg.get("content"),
                    tool_calls=calls,
                    stop_reason="tool_use",
                )

            return AgentResponse(text=msg.get("content", ""), stop_reason="end_turn")

        except Exception as exc:
            return AgentResponse(text=f"LLM error: {exc}", stop_reason="error")

    # ------------------------------------------------------------------
    # Anthropic (native tool_use)
    # ------------------------------------------------------------------

    def _anthropic_turn(
        self, messages: list[dict], tools: list[dict], system_prompt: str,
    ) -> AgentResponse:
        adapter = getattr(self._client, "_adapter", None) or getattr(self._client, "_explicit_adapter", None)
        if adapter is None:
            return self._text_turn(messages, tools, system_prompt)

        # Build Anthropic messages
        anth_messages = []
        for m in messages:
            role = m.get("role", "user")
            if role == "tool_result":
                anth_messages.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": m.get("tool_call_id", ""), "content": json.dumps(m.get("content", {}), ensure_ascii=False)}],
                })
            elif role == "assistant" and m.get("tool_calls"):
                content = []
                if m.get("content"):
                    content.append({"type": "text", "text": m["content"]})
                for tc in m["tool_calls"]:
                    content.append({"type": "tool_use", "id": tc.get("call_id", ""), "name": tc.get("tool_id", ""), "input": tc.get("params", {})})
                anth_messages.append({"role": "assistant", "content": content})
            else:
                anth_messages.append({"role": role, "content": m.get("content", "")})

        anth_tools = [{"name": t["name"], "description": t.get("description", ""), "input_schema": t.get("parameters", {})} for t in tools]

        try:
            client = getattr(adapter, "_client", None) or getattr(adapter, "client", None)
            if client is None:
                return self._text_turn(messages, tools, system_prompt)

            model = getattr(adapter, "_model", None) or getattr(adapter, "model", "claude-sonnet-4-20250514")
            response = client.messages.create(
                model=model,
                system=system_prompt,
                messages=anth_messages,
                tools=anth_tools,
                max_tokens=4096,
            )

            text_parts = []
            calls = []
            for block in response.content:
                if block.type == "text":
                    text_parts.append(block.text)
                elif block.type == "tool_use":
                    calls.append(ToolCall(tool_id=block.name, params=block.input or {}, call_id=block.id))

            return AgentResponse(
                text="\n".join(text_parts) if text_parts else None,
                tool_calls=calls if calls else None,
                stop_reason="tool_use" if calls else "end_turn",
            )

        except Exception as exc:
            return AgentResponse(text=f"LLM error: {exc}", stop_reason="error")

    # ------------------------------------------------------------------
    # Text-based fallback (Ollama, Gemini, any provider)
    # ------------------------------------------------------------------

    def _native_turn(
        self, adapter: Any, messages: list[dict], tools: list[dict], system_prompt: str,
    ) -> AgentResponse:
        """Use the adapter's native function calling (bypasses Cloudflare)."""
        # Build OpenAI-format messages
        oai_messages = [{"role": "system", "content": system_prompt}]
        for m in messages:
            role = m.get("role", "user")
            if role == "tool_result":
                oai_messages.append({
                    "role": "tool",
                    "tool_call_id": m.get("tool_call_id", ""),
                    "content": json.dumps(m.get("content", {}), ensure_ascii=False)[:2000],
                })
            elif role == "assistant" and m.get("tool_calls"):
                tc_list = []
                for tc in m["tool_calls"]:
                    tc_list.append({
                        "id": tc.get("call_id", ""),
                        "type": "function",
                        "function": {"name": tc.get("tool_id", ""), "arguments": json.dumps(tc.get("params", {}))},
                    })
                oai_messages.append({"role": "assistant", "content": m.get("content", ""), "tool_calls": tc_list})
            else:
                oai_messages.append({"role": role, "content": m.get("content", "")})

        # Rate limit check — enforce wait instead of rejecting
        allowed, wait_s = self._rate_limiter.check()
        if not allowed and wait_s > 0:
            import time
            time.sleep(min(wait_s, 30))  # Wait but cap at 30s
            self._rate_limiter.check()  # Re-register after wait

        data = adapter.complete_with_tools(oai_messages, tools)
        choice = data.get("choices", [{}])[0]
        msg = choice.get("message", {})

        raw_tool_calls = msg.get("tool_calls")
        if raw_tool_calls:
            calls = []
            for tc in raw_tool_calls:
                fn = tc.get("function", {})
                try:
                    params = json.loads(fn.get("arguments", "{}"))
                except json.JSONDecodeError:
                    params = {}
                calls.append(ToolCall(
                    tool_id=fn.get("name", ""),
                    params=params,
                    call_id=tc.get("id", ""),
                ))
            return AgentResponse(
                text=msg.get("content"),
                tool_calls=calls,
                stop_reason="tool_use",
            )

        return AgentResponse(text=msg.get("content", ""), stop_reason="end_turn")

    def _text_turn(
        self, messages: list[dict], tools: list[dict], system_prompt: str,
    ) -> AgentResponse:
        # Build a text prompt that includes tool definitions
        tools_text = "Available tools:\n"
        for t in tools[:30]:  # Limit to avoid prompt bloat
            params_desc = ", ".join(
                f"{p}: {info.get('type', 'string')}"
                for p, info in t.get("parameters", {}).get("properties", {}).items()
            )
            tools_text += f"- {t['name']}({params_desc}): {t.get('description', '')[:100]}\n"

        tools_text += """
CRITICAL RULES:
1. To call a tool, respond with ONLY this JSON (nothing else):
   {"tool_calls": [{"tool_id": "tool_name", "params": {"param1": "value1"}}]}

2. To respond to the user, write normal text WITHOUT any JSON.

3. NEVER mix text and JSON in the same response.
4. NEVER invent or hallucinate tool results. You MUST call the tool and wait for the actual result.
5. After you receive a tool result, analyze it and respond to the user.
"""

        full_prompt = f"{system_prompt}\n\n{tools_text}"

        # Build conversation text
        conv = ""
        for m in messages:
            role = m.get("role", "user")
            if role == "tool_result":
                conv += f"\nTool result ({m.get('tool_id', '')}):\n{json.dumps(m.get('content', {}), ensure_ascii=False)[:1000]}\n"
            else:
                conv += f"\n{role}: {m.get('content', '')}\n"

        # Rate limit check — enforce wait instead of rejecting
        allowed, wait_s = self._rate_limiter.check()
        if not allowed and wait_s > 0:
            import time
            time.sleep(min(wait_s, 30))
            self._rate_limiter.check()

        try:
            response_text = self._client.complete(system_prompt=full_prompt, user_prompt=conv)
        except Exception as exc:
            return AgentResponse(text=f"LLM error: {exc}", stop_reason="error")

        # Try to parse tool calls from the response
        calls = self._parse_tool_calls_from_text(response_text)
        if calls:
            return AgentResponse(tool_calls=calls, stop_reason="tool_use")

        return AgentResponse(text=response_text, stop_reason="end_turn")

    @staticmethod
    def _parse_tool_calls_from_text(text: str) -> list[ToolCall] | None:
        """Extract tool_calls JSON from text, even if mixed with natural language."""
        if "tool_calls" not in text:
            return None

        # Find the start of the JSON object containing tool_calls
        idx = text.find('"tool_calls"')
        if idx < 0:
            return None

        # Walk backwards to find the opening {
        start = text.rfind("{", 0, idx)
        if start < 0:
            return None

        # Use json.JSONDecoder to extract the complete JSON object
        decoder = json.JSONDecoder()
        try:
            data, _ = decoder.raw_decode(text, start)
            raw_calls = data.get("tool_calls", [])
            if isinstance(raw_calls, list) and raw_calls:
                calls = []
                for rc in raw_calls:
                    tid = rc.get("tool_id") or rc.get("name", "")
                    params = rc.get("params") or rc.get("arguments") or rc.get("inputs") or {}
                    if tid:
                        calls.append(ToolCall(tool_id=tid, params=params))
                return calls if calls else None
        except (json.JSONDecodeError, ValueError):
            pass

        return None
