"""Gap Detector — identifies capabilities users need but don't exist.

Analyzes recent execution history for patterns of failure:
- "unknown" suggestions from the interpreter
- "capability_not_found" errors
- Repeated similar requests that failed

When a gap is detected 3+ times, triggers auto-skill creation via Claude.
"""
from __future__ import annotations

import threading
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any


class GapDetector:
    """Detects missing capabilities from execution patterns."""

    def __init__(
        self,
        execution_history: Any = None,
        claude_bridge: Any = None,
        skill_creator: Any = None,
        threshold: int = 3,
        interval_s: int = 900,
    ) -> None:
        self._history = execution_history
        self._claude = claude_bridge
        self._skill_creator = skill_creator
        self._threshold = threshold
        self._interval = interval_s
        self._running = False
        self._thread: threading.Thread | None = None
        self._detected_gaps: list[dict[str, Any]] = []
        self._auto_created: list[dict[str, Any]] = []
        self._processed_patterns: set[str] = set()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="gap-detector")
        self._thread.start()
        print("[GAP-DETECTOR] Started", flush=True)

    def stop(self) -> None:
        self._running = False

    @property
    def detected_gaps(self) -> list[dict[str, Any]]:
        return list(self._detected_gaps)

    @property
    def auto_created(self) -> list[dict[str, Any]]:
        return list(self._auto_created)

    def scan_now(self) -> list[dict[str, Any]]:
        """Run gap detection immediately."""
        return self._detect()

    def _loop(self) -> None:
        time.sleep(60)  # Initial delay
        while self._running:
            try:
                gaps = self._detect()
                for gap in gaps:
                    if gap["pattern"] not in self._processed_patterns:
                        self._try_auto_create(gap)
                        self._processed_patterns.add(gap["pattern"])
            except Exception as exc:
                print(f"[GAP-DETECTOR] Error: {exc}", flush=True)
            time.sleep(self._interval)

    def _detect(self) -> list[dict[str, Any]]:
        """Analyze history for capability gaps and tool failure patterns."""
        if self._history is None:
            return []

        gaps = []
        failure_patterns: Counter[str] = Counter()
        tool_failures: Counter[str] = Counter()

        try:
            # Get recent history
            history = self._history.get_recent(limit=50) if hasattr(self._history, "get_recent") else []
            if not history:
                history = self._read_history_file()

            for entry in history:
                status = entry.get("status", "")
                intent = entry.get("intent", "")
                error = entry.get("error_message", "")

                # Detect "unknown" — interpreter couldn't match a capability
                if status in ("unknown", "error") and intent:
                    pattern = self._normalize(intent)
                    failure_patterns[pattern] += 1

                # Detect specific error codes
                if "capability_not_found" in str(error) or "not registered" in str(error):
                    pattern = self._normalize(intent)
                    failure_patterns[pattern] += 1

                # Detect repeated tool failures from messages
                messages = entry.get("messages", [])
                for msg in messages:
                    if isinstance(msg, dict) and msg.get("role") == "tool":
                        content = msg.get("content", "")
                        if isinstance(content, str) and "error" in content.lower():
                            tool_id = msg.get("name", msg.get("tool_id", "unknown_tool"))
                            tool_failures[tool_id] += 1

        except Exception:
            pass

        # Capability gaps: patterns that exceed threshold
        for pattern, count in failure_patterns.items():
            if count >= self._threshold:
                gap = {
                    "pattern": pattern,
                    "count": count,
                    "type": "capability_gap",
                    "detected_at": _now(),
                    "status": "detected",
                }
                gaps.append(gap)
                if not any(g["pattern"] == pattern for g in self._detected_gaps):
                    self._detected_gaps.append(gap)

        # Tool failure gaps: tools failing 3+ times
        for tool_id, count in tool_failures.items():
            if count >= self._threshold:
                pattern = f"tool_failure:{tool_id}"
                gap = {
                    "pattern": pattern,
                    "tool_id": tool_id,
                    "count": count,
                    "type": "tool_failure",
                    "detected_at": _now(),
                    "status": "detected",
                }
                gaps.append(gap)
                if not any(g["pattern"] == pattern for g in self._detected_gaps):
                    self._detected_gaps.append(gap)

        return gaps

    def get_summary(self) -> dict[str, Any]:
        """Return a summary of detected gaps for the supervisor UI."""
        capability_gaps = [g for g in self._detected_gaps if g.get("type") != "tool_failure"]
        tool_gaps = [g for g in self._detected_gaps if g.get("type") == "tool_failure"]
        return {
            "total_gaps": len(self._detected_gaps),
            "capability_gaps": len(capability_gaps),
            "tool_failure_gaps": len(tool_gaps),
            "auto_created": len(self._auto_created),
            "top_patterns": [
                {"pattern": g["pattern"], "count": g["count"]}
                for g in sorted(self._detected_gaps, key=lambda x: x.get("count", 0), reverse=True)[:5]
            ],
        }

    def _try_auto_create(self, gap: dict[str, Any]) -> None:
        """Try to auto-create a skill for a detected gap."""
        if not self._claude or not self._claude.available:
            return
        if not self._skill_creator:
            return

        print(f"[GAP-DETECTOR] Auto-creating skill for: {gap['pattern']}", flush=True)

        try:
            # Ask Claude to design the skill
            skill_spec = self._claude.design_skill(
                f"Users frequently request: '{gap['pattern']}'. Create a tool for this.",
                reference_tools=[
                    "system/tools/contracts/v1/filesystem_read_file.json",
                    "system/tools/contracts/v1/network_http_get.json",
                ],
            )

            if skill_spec and skill_spec.get("tool_id"):
                # Hot-load the skill
                result = self._skill_creator.create_and_load(
                    tool_id=skill_spec["tool_id"],
                    name=skill_spec.get("name", ""),
                    description=skill_spec.get("description", ""),
                    inputs=skill_spec.get("inputs", {}),
                    outputs=skill_spec.get("outputs", {}),
                    handler_code=skill_spec.get("handler_code", ""),
                    handler_name=skill_spec.get("handler_name", ""),
                    dependencies=skill_spec.get("dependencies"),
                )

                if result.get("status") == "success":
                    record = {
                        "pattern": gap["pattern"],
                        "tool_id": skill_spec["tool_id"],
                        "created_at": _now(),
                        "auto": True,
                    }
                    self._auto_created.append(record)
                    gap["status"] = "resolved"
                    print(f"[GAP-DETECTOR] Auto-created: {skill_spec['tool_id']}", flush=True)

                    # Notify
                    try:
                        from system.core.ui_bridge.event_bus import event_bus
                        event_bus.emit("supervisor_alert", {
                            "severity": "info",
                            "source": "gap_detector",
                            "message": f"New skill auto-created: {skill_spec['tool_id']} (pattern: {gap['pattern']})",
                        })
                    except Exception:
                        pass

        except Exception as exc:
            print(f"[GAP-DETECTOR] Auto-create failed: {exc}", flush=True)

    def _read_history_file(self) -> list[dict[str, Any]]:
        """Fallback: read history directly from file."""
        import json
        from pathlib import Path
        for p in [Path("C:/data/workspace/memory/history.json"), Path("/data/workspace/memory/history.json")]:
            if p.exists():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    return data.get("sessions", data.get("history", []))[:50]
                except Exception:
                    pass
        return []

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize intent text to find patterns."""
        import re
        text = text.lower().strip()
        text = re.sub(r'["\'].*?["\']', 'X', text)  # Replace quoted strings
        text = re.sub(r'\b\d+\b', 'N', text)  # Replace numbers
        text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
        # Simple suffix removal for better pattern matching
        text = re.sub(r'\b(\w+)(ing|ed|tion|ment|ness)\b', r'\1', text)
        return text[:80]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
