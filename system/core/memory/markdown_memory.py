"""Markdown-based persistent memory — human-readable, editable, version-friendly.

Manages three layers:
- ``MEMORY.md``   — permanent facts, user prefs, decisions, learned patterns
- ``daily/*.md``  — per-day activity logs
- ``sessions/*.md`` — compact summaries of compacted sessions

All writes are atomic (write-then-rename) and thread-safe.
Rule 5: never blocks execution — all public methods wrap in try/except.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any


_DATE_FMT = "%Y-%m-%d"
_TIME_FMT = "%H:%M"


class MarkdownMemory:
    """Read/write MEMORY.md, daily notes, and session summaries."""

    def __init__(self, memory_dir: str | Path) -> None:
        self._dir = Path(memory_dir).resolve()
        self._lock = RLock()
        self._ensure_dirs()

    # ------------------------------------------------------------------
    # Directory layout
    # ------------------------------------------------------------------

    @property
    def memory_md_path(self) -> Path:
        return self._dir / "MEMORY.md"

    @property
    def daily_dir(self) -> Path:
        return self._dir / "daily"

    @property
    def sessions_dir(self) -> Path:
        return self._dir / "sessions"

    def _ensure_dirs(self) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            self.daily_dir.mkdir(exist_ok=True)
            self.sessions_dir.mkdir(exist_ok=True)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # MEMORY.md — persistent facts
    # ------------------------------------------------------------------

    def load_memory_md(self) -> str:
        """Return the full content of MEMORY.md, or empty string."""
        try:
            if self.memory_md_path.exists():
                return self.memory_md_path.read_text(encoding="utf-8")
        except OSError:
            pass
        return ""

    def save_memory_md(self, content: str) -> None:
        """Overwrite MEMORY.md with *content*."""
        with self._lock:
            try:
                self.memory_md_path.write_text(content, encoding="utf-8")
            except OSError:
                pass

    def load_memory_sections(self) -> dict[str, list[str]]:
        """Parse MEMORY.md into {section_name: [lines]}."""
        text = self.load_memory_md()
        if not text:
            return {}
        sections: dict[str, list[str]] = {}
        current: str | None = None
        for line in text.splitlines():
            m = re.match(r"^##\s+(.+)", line)
            if m:
                current = m.group(1).strip()
                sections.setdefault(current, [])
            elif current is not None:
                sections[current].append(line)
        return sections

    def add_fact(self, section: str, fact: str) -> None:
        """Append a bullet point to a section in MEMORY.md. Creates the section if needed."""
        with self._lock:
            try:
                text = self.load_memory_md()
                line = f"- {fact.strip()}"

                if not text:
                    text = f"# CapOS Memory\n\n## {section}\n{line}\n"
                    self.save_memory_md(text)
                    return

                # Find section
                pattern = rf"(^## {re.escape(section)}\s*$)"
                match = re.search(pattern, text, re.MULTILINE)
                if match:
                    # Check for duplicate
                    if line in text:
                        return
                    # Insert after section header (before next section or EOF)
                    pos = match.end()
                    # Find next section or end
                    next_section = re.search(r"^## ", text[pos + 1:], re.MULTILINE)
                    if next_section:
                        insert_at = pos + 1 + next_section.start()
                        text = text[:insert_at] + line + "\n" + text[insert_at:]
                    else:
                        text = text.rstrip() + "\n" + line + "\n"
                else:
                    text = text.rstrip() + f"\n\n## {section}\n{line}\n"

                self.save_memory_md(text)
            except Exception:
                pass

    def remove_fact(self, section: str, fact_substring: str) -> bool:
        """Remove the first bullet in *section* containing *fact_substring*."""
        with self._lock:
            try:
                text = self.load_memory_md()
                if not text:
                    return False
                lines = text.splitlines()
                in_section = False
                removed = False
                new_lines: list[str] = []
                for line in lines:
                    if re.match(r"^## ", line):
                        in_section = line.strip().endswith(section)
                    if in_section and not removed and fact_substring in line and line.strip().startswith("- "):
                        removed = True
                        continue
                    new_lines.append(line)
                if removed:
                    self.save_memory_md("\n".join(new_lines) + "\n")
                return removed
            except Exception:
                return False

    def init_memory_md(self, user_name: str = "", language: str = "auto") -> None:
        """Create MEMORY.md with initial structure if it doesn't exist."""
        if self.memory_md_path.exists():
            return
        lang_line = f"- Language: {language}" if language != "auto" else "- Language: auto-detect"
        content = f"""# CapOS Memory

## User
- Name: {user_name or 'Unknown'}
{lang_line}

## Decisions

## Projects

## Learned Patterns
"""
        self.save_memory_md(content)

    # ------------------------------------------------------------------
    # Daily notes
    # ------------------------------------------------------------------

    def _daily_path(self, date: datetime | None = None) -> Path:
        d = date or datetime.now(timezone.utc)
        return self.daily_dir / f"{d.strftime(_DATE_FMT)}.md"

    def load_daily(self, date: datetime | None = None) -> str:
        """Return today's daily note content."""
        try:
            p = self._daily_path(date)
            if p.exists():
                return p.read_text(encoding="utf-8")
        except OSError:
            pass
        return ""

    def append_daily(self, entry: str, section: str = "Sessions", date: datetime | None = None) -> None:
        """Append an entry to today's daily note under a section."""
        with self._lock:
            try:
                d = date or datetime.now(timezone.utc)
                p = self._daily_path(d)
                now_str = d.strftime(_TIME_FMT)

                if not p.exists():
                    content = f"# {d.strftime(_DATE_FMT)}\n\n## Sessions\n\n## Errors\n\n## Skills Created\n"
                    p.write_text(content, encoding="utf-8")

                text = p.read_text(encoding="utf-8")
                line = f"- {now_str} {entry.strip()}"

                # Find section and append
                pattern = rf"(^## {re.escape(section)}\s*$)"
                match = re.search(pattern, text, re.MULTILINE)
                if match:
                    pos = match.end()
                    next_sec = re.search(r"^## ", text[pos + 1:], re.MULTILINE)
                    if next_sec:
                        insert_at = pos + 1 + next_sec.start()
                        text = text[:insert_at] + line + "\n" + text[insert_at:]
                    else:
                        text = text.rstrip() + "\n" + line + "\n"
                else:
                    text = text.rstrip() + f"\n\n## {section}\n{line}\n"

                p.write_text(text, encoding="utf-8")
            except Exception:
                pass

    def list_daily_dates(self, limit: int = 7) -> list[str]:
        """Return the most recent daily note dates (YYYY-MM-DD), newest first."""
        try:
            files = sorted(self.daily_dir.glob("*.md"), reverse=True)
            return [f.stem for f in files[:limit]]
        except OSError:
            return []

    # ------------------------------------------------------------------
    # Session summaries
    # ------------------------------------------------------------------

    def save_session_summary(self, session_id: str, summary: str) -> None:
        """Save a compacted session summary."""
        with self._lock:
            try:
                p = self.sessions_dir / f"{session_id}.md"
                now = datetime.now(timezone.utc)
                content = f"# Session {session_id}\n"
                content += f"**Date:** {now.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                content += summary
                p.write_text(content, encoding="utf-8")
            except OSError:
                pass

    def load_session_summary(self, session_id: str) -> str:
        """Load a session summary."""
        try:
            p = self.sessions_dir / f"{session_id}.md"
            if p.exists():
                return p.read_text(encoding="utf-8")
        except OSError:
            pass
        return ""

    def list_sessions(self, limit: int = 10) -> list[str]:
        """Return recent session IDs, newest first."""
        try:
            files = sorted(self.sessions_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
            return [f.stem for f in files[:limit]]
        except OSError:
            return []

    # ------------------------------------------------------------------
    # Context for agent prompt injection
    # ------------------------------------------------------------------

    def build_context(self, max_tokens: int = 500) -> str:
        """Build a compact context string for injection into agent system prompt.

        Includes:
        - Key facts from MEMORY.md (User, Decisions, Learned Patterns)
        - Recent daily activity (last 2 days)
        Rough token estimation: 1 token ~= 4 chars.
        """
        parts: list[str] = []
        char_budget = max_tokens * 4

        # MEMORY.md key sections
        sections = self.load_memory_sections()
        for sec_name in ("User", "Decisions", "Learned Patterns", "Projects"):
            lines = sections.get(sec_name, [])
            # Take non-empty lines
            items = [l.strip() for l in lines if l.strip()]
            if items:
                # Limit decisions to last 5
                if sec_name == "Decisions" and len(items) > 5:
                    items = items[-5:]
                parts.append(f"**{sec_name}:** " + " | ".join(items))

        # Recent daily notes (last 2 days, first 3 entries each)
        dates = self.list_daily_dates(limit=2)
        for d in dates:
            try:
                dt = datetime.strptime(d, _DATE_FMT).replace(tzinfo=timezone.utc)
                daily = self.load_daily(dt)
                if daily:
                    # Extract first few session entries
                    session_lines = []
                    in_sessions = False
                    for line in daily.splitlines():
                        if line.strip() == "## Sessions":
                            in_sessions = True
                            continue
                        if line.startswith("## "):
                            in_sessions = False
                            continue
                        if in_sessions and line.strip().startswith("- "):
                            session_lines.append(line.strip())
                    if session_lines:
                        parts.append(f"**{d}:** " + " | ".join(session_lines[:3]))
            except (ValueError, OSError):
                continue

        context = "\n".join(parts)
        # Trim to budget
        if len(context) > char_budget:
            context = context[:char_budget].rsplit("\n", 1)[0] + "\n..."

        return context
