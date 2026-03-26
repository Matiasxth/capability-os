from __future__ import annotations

import json
import re
from typing import Any

from system.capabilities.registry import CapabilityRegistry

from .capability_matcher import CapabilityMatchError, CapabilityMatcher
from .input_extractor import InputExtractionError, InputExtractor
from .llm_client import LLMClient, LLMClientError
from .prompts import BASE_RESTRICTIVE_PROMPT, build_intent_prompt


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
    ):
        self.capability_registry = capability_registry
        self.llm_client = llm_client or LLMClient()
        self.input_extractor = input_extractor or InputExtractor()
        self.capability_matcher = capability_matcher or CapabilityMatcher(capability_registry)

    def interpret(self, user_text: str) -> dict[str, Any]:
        if not isinstance(user_text, str) or not user_text.strip():
            raise IntentInterpreterError("Field 'text' must be a non-empty string.")

        prompt = build_intent_prompt(user_text, self.capability_registry.ids())
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
