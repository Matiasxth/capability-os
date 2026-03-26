from __future__ import annotations

from typing import Iterable


BASE_RESTRICTIVE_PROMPT = """
You are an intent parser for Capability OS.
Rules:
1. Return only valid JSON.
2. Never execute anything.
3. Never invent capabilities, tools, domains, or state names.
4. Only suggest:
   - {"type":"capability","capability":"<id>","inputs":{...}}
   - {"type":"sequence","steps":[...]}
   - {"type":"unknown"}
5. If intent is ambiguous, return {"type":"unknown"}.
6. Do not include prose, markdown, or code fences.
""".strip()


INTENT_PROMPT_TEMPLATE = """
User text:
{user_text}

Available capabilities:
{capability_ids}

Interpret the user text and return JSON only.
""".strip()


def build_intent_prompt(user_text: str, capability_ids: Iterable[str]) -> str:
    cap_list = ", ".join(sorted(set(capability_ids)))
    return INTENT_PROMPT_TEMPLATE.format(user_text=user_text.strip(), capability_ids=cap_list)
