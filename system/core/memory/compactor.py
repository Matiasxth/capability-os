"""Auto-compaction — detects when conversation context is too large and
compresses it, saving summaries to markdown memory.

Flow:
1. ``should_compact()`` checks if messages exceed a token threshold.
2. ``compact()`` uses the LLM to generate a summary + extract permanent facts.
3. Summary saved to ``sessions/{id}.md`` and daily note.
4. Facts merged into ``MEMORY.md``.
5. Messages replaced with a compact system-injected summary.

Rule 5: never blocks execution.
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Any

from .markdown_memory import MarkdownMemory


def _estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough token estimation: 1 token ~= 4 chars."""
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, dict):
            total += len(str(content))
        elif isinstance(content, list):
            total += sum(len(str(item)) for item in content)
    return total // 4


COMPACT_PROMPT = """You are a memory compactor. Analyze the following conversation and produce TWO sections:

## Summary
A concise summary of what happened in this conversation (3-5 sentences). Include:
- What the user asked for
- What tools were called and results
- Any errors or retries
- Final outcome

## Facts
Extract ONLY permanent facts worth remembering for future conversations. Each fact on its own line starting with "- ". Examples:
- User preference discovered
- Important decision made
- System configuration changed
- Recurring error pattern

If no permanent facts were discovered, write "- No new facts"

CONVERSATION:
{conversation}
"""


class MemoryCompactor:
    """Detects context overflow and compacts conversation history."""

    def __init__(
        self,
        markdown_memory: MarkdownMemory,
        max_context_tokens: int = 4000,
        compact_threshold: float = 0.80,
    ) -> None:
        self._md = markdown_memory
        self._max_tokens = max_context_tokens
        self._threshold = compact_threshold

    def should_compact(self, messages: list[dict[str, Any]]) -> bool:
        """Return True if messages exceed the compaction threshold."""
        if len(messages) < 4:
            return False
        tokens = _estimate_tokens(messages)
        return tokens > int(self._max_tokens * self._threshold)

    def compact(
        self,
        messages: list[dict[str, Any]],
        llm_complete: Any = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Compact messages using LLM summarization.

        Args:
            messages: The conversation messages to compact.
            llm_complete: Callable(prompt: str) -> str. If None, uses a simple extractive summary.
            session_id: Session identifier. Auto-generated if not provided.

        Returns:
            {
                "summary": str,
                "facts": list[str],
                "compacted_messages": list[dict],
                "session_id": str,
                "tokens_before": int,
                "tokens_after": int,
            }
        """
        sid = session_id or f"session_{uuid.uuid4().hex[:8]}"
        tokens_before = _estimate_tokens(messages)

        # Build conversation text for the LLM
        conv_lines: list[str] = []
        for m in messages:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            if isinstance(content, dict):
                content = str(content)[:200]
            elif isinstance(content, list):
                content = " ".join(str(x)[:100] for x in content)
            if isinstance(content, str) and len(content) > 500:
                content = content[:500] + "..."
            conv_lines.append(f"[{role}] {content}")
        conversation_text = "\n".join(conv_lines)

        # Generate summary
        summary = ""
        facts: list[str] = []

        if llm_complete is not None:
            try:
                prompt = COMPACT_PROMPT.format(conversation=conversation_text)
                raw = llm_complete(prompt)
                summary, facts = self._parse_compact_response(raw)
            except Exception:
                summary = self._extractive_summary(messages)
                facts = []
        else:
            summary = self._extractive_summary(messages)

        # Save session summary to markdown
        try:
            self._md.save_session_summary(sid, summary)
        except Exception:
            pass

        # Save facts to MEMORY.md
        for fact in facts:
            if fact.lower().strip("- ") != "no new facts":
                try:
                    self._md.add_fact("Learned Patterns", fact)
                except Exception:
                    pass

        # Log to daily notes
        try:
            entry_count = len(messages)
            self._md.append_daily(
                f"Session {sid} compacted ({entry_count} messages → summary)",
                section="Sessions",
            )
        except Exception:
            pass

        # Build compacted messages: system summary + keep last 2 user/assistant exchanges
        compacted: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": f"[Previous conversation summary]\n{summary}\n\n[Conversation continues below]",
            }
        ]

        # Keep the last few messages for continuity
        keep_count = min(4, len(messages))
        if keep_count > 0:
            compacted.extend(messages[-keep_count:])

        tokens_after = _estimate_tokens(compacted)

        return {
            "summary": summary,
            "facts": facts,
            "compacted_messages": compacted,
            "session_id": sid,
            "tokens_before": tokens_before,
            "tokens_after": tokens_after,
        }

    def _parse_compact_response(self, raw: str) -> tuple[str, list[str]]:
        """Parse LLM response into (summary, facts)."""
        summary = ""
        facts: list[str] = []

        # Extract Summary section
        summary_match = re.search(r"##\s*Summary\s*\n(.*?)(?=##|\Z)", raw, re.DOTALL)
        if summary_match:
            summary = summary_match.group(1).strip()

        # Extract Facts section
        facts_match = re.search(r"##\s*Facts\s*\n(.*?)(?=##|\Z)", raw, re.DOTALL)
        if facts_match:
            for line in facts_match.group(1).splitlines():
                line = line.strip()
                if line.startswith("- ") and len(line) > 3:
                    facts.append(line[2:].strip())

        if not summary:
            summary = raw[:500]

        return summary, facts

    def _extractive_summary(self, messages: list[dict[str, Any]]) -> str:
        """Fallback: build a summary without LLM by extracting key messages."""
        parts: list[str] = []
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "user" and isinstance(content, str):
                parts.append(f"User: {content[:100]}")
            elif role == "assistant" and isinstance(content, str) and len(content) > 10:
                parts.append(f"Assistant: {content[:100]}")
        # Keep first 2 and last 2
        if len(parts) > 6:
            parts = parts[:3] + ["..."] + parts[-3:]
        return "\n".join(parts)
