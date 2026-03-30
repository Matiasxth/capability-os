"""Claude Bridge — invokes Claude Code CLI for analysis, fixes, and skill generation.

Rate-limited to prevent excessive API usage.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any


class ClaudeBridge:
    """Interface to invoke Claude Code CLI from the system."""

    def __init__(self, project_root: Path, max_per_hour: int = 10) -> None:
        self._root = project_root
        self._max_per_hour = max_per_hour
        self._timestamps: deque[float] = deque()
        self._lock = threading.Lock()
        self._log: list[dict[str, Any]] = []

    def analyze(self, prompt: str, timeout_s: int = 300) -> str:
        """Ask Claude to analyze a problem. Returns text response."""
        if not self._rate_check():
            return "[Rate limited — max invocations per hour reached]"

        try:
            result = subprocess.run(
                ["claude", "-p", prompt],
                cwd=str(self._root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
            )
            response = result.stdout.strip()
            self._log_action("analyze", prompt[:100], len(response))
            return response
        except FileNotFoundError:
            return "[Claude CLI not found in PATH]"
        except subprocess.TimeoutExpired:
            return "[Claude timeout — analysis took too long]"
        except Exception as exc:
            return f"[Claude error: {exc}]"

    def fix_error(self, error: str, file_path: str) -> dict[str, Any]:
        """Ask Claude to fix an error in a specific file."""
        content = ""
        p = Path(file_path)
        if p.exists():
            content = p.read_text(encoding="utf-8", errors="replace")[:3000]

        prompt = (
            f"Fix this error in Capability OS:\n\n"
            f"Error: {error}\n"
            f"File: {file_path}\n\n"
            f"Code:\n{content}\n\n"
            f"Return JSON: {{\"fixed_code\": \"corrected code\", \"explanation\": \"what was wrong\"}}"
        )
        response = self.analyze(prompt)
        try:
            match = re.search(r'\{[\s\S]*\}', response)
            if match:
                return json.loads(match.group(0))
        except (json.JSONDecodeError, AttributeError):
            pass
        return {"explanation": response}

    def design_skill(self, description: str, reference_tools: list[str] | None = None) -> dict[str, Any]:
        """Ask Claude to design a complete tool/skill."""
        refs = ""
        if reference_tools:
            for ref in reference_tools[:3]:
                p = self._root / ref
                if p.exists():
                    refs += f"\n--- {ref} ---\n{p.read_text(encoding='utf-8', errors='replace')[:800]}\n"

        prompt = (
            f"Design a Capability OS tool for: {description}\n\n"
            f"Return ONLY a JSON object:\n"
            f'{{"tool_id": "snake_case_id", "name": "Display Name", '
            f'"description": "what it does", '
            f'"inputs": {{"param": {{"type": "string", "required": true, "description": "..."}}}}, '
            f'"outputs": {{"result": {{"type": "string"}}}}, '
            f'"handler_code": "def handle_tool_id(params, contract):\\n    ...\\n    return {{...}}", '
            f'"handler_name": "handle_tool_id", '
            f'"dependencies": []}}\n\n'
            f"Reference:{refs}"
        )
        response = self.analyze(prompt, timeout_s=180)
        try:
            match = re.search(r'\{[\s\S]*\}', response)
            if match:
                return json.loads(match.group(0))
        except (json.JSONDecodeError, AttributeError):
            pass
        return {}

    def diagnose(self, context: str) -> str:
        """Ask Claude for a diagnosis of a system issue."""
        prompt = (
            f"Diagnose this issue in Capability OS:\n\n{context}\n\n"
            f"Provide:\n1. Root cause\n2. Impact\n3. Recommended fix\n"
            f"Be concise (3-5 sentences)."
        )
        return self.analyze(prompt, timeout_s=60)

    @property
    def available(self) -> bool:
        """Check if Claude CLI is available."""
        try:
            result = subprocess.run(["claude", "--version"], capture_output=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False

    @property
    def invocation_count(self) -> int:
        return len(self._timestamps)

    @property
    def recent_log(self) -> list[dict[str, Any]]:
        return self._log[-30:]

    def _rate_check(self) -> bool:
        now = time.monotonic()
        with self._lock:
            while self._timestamps and now - self._timestamps[0] > 3600:
                self._timestamps.popleft()
            if len(self._timestamps) >= self._max_per_hour:
                return False
            self._timestamps.append(now)
            return True

    def _log_action(self, action: str, context: str, response_len: int) -> None:
        from datetime import datetime, timezone
        self._log.append({
            "action": action,
            "context": context,
            "response_len": response_len,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        })
        if len(self._log) > 100:
            self._log = self._log[-50:]
