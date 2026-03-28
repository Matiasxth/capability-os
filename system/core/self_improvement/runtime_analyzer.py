"""Analyzes a capability gap and recommends the best resolution strategy.

Strategies are tried in priority order:
  1. existing_tool   — already in ToolRegistry
  2. mcp             — available via a configured MCP server
  3. browser         — automatable via Playwright (web UI)
  4. cli             — solvable with an existing CLI command
  5. python          — implementable in Python
  6. nodejs          — requires Node.js ecosystem
  7. not_implementable — none of the above apply

The analyzer never installs or generates anything — it only recommends.
"""
from __future__ import annotations

import re
from typing import Any

from system.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Keyword sets for heuristic classification
# ---------------------------------------------------------------------------

_BROWSER_KEYWORDS = frozenset({
    "web", "website", "browser", "page", "url", "http", "html",
    "scrape", "scraping", "form", "click", "navigate",
    "whatsapp", "gmail", "slack", "notion", "trello", "twitter",
    "linkedin", "facebook", "instagram", "github", "jira",
})

_CLI_KEYWORDS = frozenset({
    "git", "docker", "npm", "pip", "curl", "wget", "ffmpeg",
    "ssh", "scp", "rsync", "tar", "zip", "unzip", "make",
    "python", "node", "java", "gcc", "cargo", "go",
    "kubectl", "terraform", "ansible", "aws", "gcloud", "az",
})

_NODEJS_KEYWORDS = frozenset({
    "websocket", "socket.io", "electron", "puppeteer",
    "express", "npm package", "typescript", "react native",
    "next.js", "nuxt", "deno", "bun",
})

_NOT_IMPLEMENTABLE_KEYWORDS = frozenset({
    "physical", "hardware", "print document", "phone call",
    "sms", "usb", "bluetooth", "camera",
})


class RuntimeAnalyzer:
    """Recommends a resolution strategy for a capability gap."""

    def __init__(self, tool_registry: ToolRegistry | None = None):
        self._tool_registry = tool_registry

    def analyze(self, gap: dict[str, Any]) -> dict[str, Any]:
        """Analyze a gap and return the recommended strategy.

        Args:
            gap: dict with at least ``capability_id`` or ``intent`` or
                 ``suggested_capability`` and optionally ``description``.

        Returns:
            dict with ``strategy``, ``reason``, ``suggestion``, ``confidence``.
        """
        cap_id = gap.get("capability_id") or gap.get("suggested_capability") or ""
        intent = gap.get("intent") or gap.get("sample_intent") or gap.get("description") or cap_id
        text = f"{cap_id} {intent}".lower()

        # Strategy 1: existing tool
        if self._tool_registry is not None:
            match = self._find_existing_tool(cap_id, text)
            if match:
                return match

        # Strategy 2: MCP
        if "mcp" in text or "model context protocol" in text:
            return _result("mcp", "An MCP server likely provides this functionality.", "Connect a relevant MCP server and discover tools.", 0.6)

        # Strategy 7 (checked early): not implementable (phrase matching)
        if _score(text, _NOT_IMPLEMENTABLE_KEYWORDS) >= 1:
            return _result("not_implementable", "This requires physical hardware or capabilities outside software.", "Consider a manual process or dedicated hardware.", 0.9)

        # Strategy 6: Node.js (before browser — "websocket" contains "web")
        if _score(text, _NODEJS_KEYWORDS) >= 1:
            return _result("nodejs", "This requires the Node.js ecosystem.", "Generate a Node.js tool implementation.", 0.6)

        # Strategy 3: browser automation
        if _score(text, _BROWSER_KEYWORDS) >= 1:
            return _result("browser", "This looks like a web-based task automatable via browser.", "Use Playwright to automate the web interface.", 0.7)

        # Strategy 4: CLI (word boundary match to avoid "make" in "make a phone call")
        cli_match = _match_cli_word(text)
        if cli_match:
            return _result("cli", f"The CLI tool '{cli_match}' can handle this.", f"Use execution_run_command with '{cli_match}'.", 0.8)

        # Default: Python (most versatile)
        return _result("python", "This can be implemented as a Python tool.", "Generate a Python tool implementation.", 0.7)

    def _find_existing_tool(self, cap_id: str, text: str) -> dict[str, Any] | None:
        """Check if an existing tool can handle this gap."""
        if not self._tool_registry:
            return None
        # Direct match by capability_id as tool_id
        for tool_id in self._tool_registry.ids():
            # Check if the gap's capability name appears in a tool id
            if cap_id and cap_id in tool_id:
                return _result("existing_tool", f"Tool '{tool_id}' already handles this.", f"Use existing tool '{tool_id}'.", 0.95)
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _result(strategy: str, reason: str, suggestion: str, confidence: float) -> dict[str, Any]:
    return {
        "strategy": strategy,
        "reason": reason,
        "suggestion": suggestion,
        "confidence": round(confidence, 2),
    }


def _score(text: str, keywords: frozenset[str]) -> int:
    return sum(1 for kw in keywords if kw in text)


def _score_words(text: str, keywords: frozenset[str]) -> int:
    """Match keywords as whole words only."""
    words = set(re.findall(r"[a-z0-9.]+", text))
    return sum(1 for kw in keywords if kw in words)


def _match_cli_word(text: str) -> str | None:
    """Match CLI keywords as whole words to avoid false positives."""
    words = set(re.findall(r"[a-z0-9]+", text))
    for kw in sorted(_CLI_KEYWORDS, key=len, reverse=True):
        if kw in words:
            return kw
    return None
