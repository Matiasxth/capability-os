from __future__ import annotations

import json
import re
from typing import Any

from system.capabilities.registry import CapabilityRegistry

from .capability_matcher import CapabilityMatchError, CapabilityMatcher
from .input_extractor import InputExtractionError, InputExtractor
from .llm_client import LLMClient, LLMClientError
from .prompts import (
    BASE_RESTRICTIVE_PROMPT,
    CLASSIFY_SYSTEM_PROMPT,
    build_chat_prompt,
    build_classify_prompt,
    build_intent_prompt,
    build_intent_prompt_with_history,
)


class IntentInterpreterError(RuntimeError):
    """Raised when intent interpretation fails critically."""


class IntentInterpreter:
    """LLM-based intent interpretation layer with suggest_only mode."""

    def __init__(
        self,
        capability_registry: CapabilityRegistry,
        llm_client: LLMClient | None = None,
        input_extractor: InputExtractor | None = None,
        capability_matcher: CapabilityMatcher | None = None,
        workspace_registry: Any | None = None,
    ):
        self.capability_registry = capability_registry
        self.llm_client = llm_client or LLMClient()
        self.input_extractor = input_extractor or InputExtractor()
        self.capability_matcher = capability_matcher or CapabilityMatcher(capability_registry)
        self._workspace_registry = workspace_registry

    def interpret(self, user_text: str, history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if not isinstance(user_text, str) or not user_text.strip():
            raise IntentInterpreterError("Field 'text' must be a non-empty string.")

        workspaces = self._get_workspace_context()
        if history:
            prompt = build_intent_prompt_with_history(
                user_text, self.capability_registry.ids(),
                workspaces=workspaces, history=history,
            )
        else:
            prompt = build_intent_prompt(user_text, self.capability_registry.ids(), workspaces=workspaces)
        try:
            raw_response = self.llm_client.complete(
                system_prompt=BASE_RESTRICTIVE_PROMPT,
                user_prompt=prompt,
            )
        except LLMClientError as exc:
            raise IntentInterpreterError(str(exc)) from exc

        parsed = _parse_llm_json(raw_response)
        if parsed is None:
            return {
                "suggest_only": True,
                "suggestion": {"type": "unknown"},
                "error": "LLM returned invalid JSON.",
            }

        try:
            extracted = self.input_extractor.extract(parsed)
            validated = self.capability_matcher.validate(extracted)
        except (InputExtractionError, CapabilityMatchError) as exc:
            raise IntentInterpreterError(str(exc)) from exc

        return {
            "suggest_only": True,
            "suggestion": validated,
            "error": None,
        }

    def classify_message(
        self,
        text: str,
        history: list[dict[str, Any]] | None = None,
    ) -> str:
        """Classify a message as 'conversational' or 'action'.

        Returns 'action' on any failure (safer default).
        """
        if not isinstance(text, str) or not text.strip():
            return "action"
        # Fast-path: short confirmations with prior assistant context → action
        if _is_confirmation(text) and _last_assistant_suggested_action(history):
            return "action"
        try:
            raw = self.llm_client.complete(
                system_prompt=CLASSIFY_SYSTEM_PROMPT,
                user_prompt=build_classify_prompt(text, history),
            )
            word = raw.strip().lower().rstrip(".")
            if word in ("conversational", "action"):
                return word
        except Exception:
            pass
        return "action"

    def chat_response(
        self,
        text: str,
        user_name: str = "User",
        history: list[dict[str, Any]] | None = None,
    ) -> str:
        """Generate a conversational response (non-action messages)."""
        if not isinstance(text, str) or not text.strip():
            return "Hello! How can I help you?"
        workspaces = self._get_workspace_context()
        system_prompt, user_prompt = build_chat_prompt(
            text, user_name, workspaces, history,
        )
        try:
            return self.llm_client.complete(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except LLMClientError:
            return "Hello! I can help with file operations, code analysis, running commands, and more. What would you like to do?"

    def _get_workspace_context(self) -> list[dict[str, Any]] | None:
        """Build workspace list for the prompt. Returns None if no registry."""
        if self._workspace_registry is None:
            return None
        try:
            ws_list = self._workspace_registry.list()
            default_ws = self._workspace_registry.get_default()
            default_id = default_ws["id"] if default_ws else None
            result: list[dict[str, Any]] = []
            for ws in ws_list:
                result.append({
                    "name": ws.get("name", ""),
                    "path": ws.get("path", ""),
                    "access": ws.get("access", "read"),
                    "is_default": ws.get("id") == default_id,
                })
            return result if result else None
        except Exception:
            return None


_CONFIRMATIONS = frozenset({
    "si", "sí", "ok", "okay", "dale", "hazlo", "yes", "yeah", "yep",
    "claro", "adelante", "do it", "go ahead", "proceed", "sure",
    "va", "vale", "listo", "hecho", "confirmo", "ejecuta",
})


def _is_confirmation(text: str) -> bool:
    """Check if text is a short confirmation phrase."""
    normalized = text.strip().lower().rstrip(".!,")
    return normalized in _CONFIRMATIONS


def _last_assistant_suggested_action(history: list[dict[str, Any]] | None) -> bool:
    """Check if the last assistant message suggested an action (has suggested_action)."""
    if not history:
        return False
    for msg in reversed(history):
        if msg.get("role") in ("assistant", "system"):
            return bool(msg.get("suggested_action"))
    return False


def _parse_llm_json(raw: str) -> dict[str, Any] | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        return None
    return None
