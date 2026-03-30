"""Domain Registry — groups related tools into skill domains.

Instead of one skill per tool, tools are organized by domain:
  pdf_tools/ → pdf_to_text, pdf_merge, pdf_annotate
  image_tools/ → image_resize, image_convert, image_compress

When creating a new tool, the registry finds the matching domain
or creates a new one. Each domain has a SKILL.md and manifest.json.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any


# Keyword → domain mapping for auto-classification
DOMAIN_KEYWORDS = {
    "pdf_tools": ["pdf", "document", "word", "docx", "page"],
    "image_tools": ["image", "photo", "picture", "resize", "convert", "png", "jpg", "svg"],
    "data_tools": ["csv", "excel", "spreadsheet", "data", "parse", "transform", "json"],
    "web_tools": ["http", "url", "scrape", "fetch", "api", "rest", "webhook"],
    "file_tools": ["file", "directory", "folder", "zip", "compress", "archive"],
    "text_tools": ["text", "string", "regex", "format", "translate", "summarize"],
    "audio_tools": ["audio", "sound", "music", "mp3", "wav", "voice"],
    "video_tools": ["video", "mp4", "stream", "record"],
    "email_tools": ["email", "mail", "smtp", "inbox"],
    "crypto_tools": ["encrypt", "decrypt", "hash", "password", "token"],
    "math_tools": ["calculate", "math", "statistics", "number", "formula"],
    "calendar_tools": ["calendar", "schedule", "event", "reminder", "date", "time"],
}


class DomainRegistry:
    """Manages skill domains — groups of related tools."""

    def __init__(self, skills_dir: str | Path) -> None:
        self._dir = Path(skills_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._domains: dict[str, dict[str, Any]] = {}
        self._load()

    def find_domain(self, description: str) -> str | None:
        """Find existing domain that matches a description."""
        desc_lower = description.lower()

        # Check existing domains first
        for domain_id, domain in self._domains.items():
            keywords = domain.get("keywords", [])
            for kw in keywords:
                if kw in desc_lower:
                    return domain_id

        # Check predefined keyword map
        for domain_id, keywords in DOMAIN_KEYWORDS.items():
            for kw in keywords:
                if kw in desc_lower:
                    # Check if this domain exists
                    if domain_id in self._domains:
                        return domain_id
                    return None  # Domain would match but doesn't exist yet

        return None

    def suggest_domain(self, description: str) -> str:
        """Suggest a domain ID for a new tool based on description."""
        desc_lower = description.lower()
        for domain_id, keywords in DOMAIN_KEYWORDS.items():
            for kw in keywords:
                if kw in desc_lower:
                    return domain_id
        # Generic fallback
        words = desc_lower.split()[:2]
        return "_".join(w for w in words if w.isalnum())[:20] + "_tools"

    def create_domain(self, domain_id: str, name: str, description: str) -> dict[str, Any]:
        """Create a new skill domain."""
        with self._lock:
            domain_dir = self._dir / domain_id
            domain_dir.mkdir(parents=True, exist_ok=True)
            (domain_dir / "contracts").mkdir(exist_ok=True)
            (domain_dir / "handlers").mkdir(exist_ok=True)

            # Extract keywords from description
            keywords = [w for w in description.lower().split() if len(w) > 3 and w.isalpha()][:10]

            manifest = {
                "id": domain_id,
                "name": name,
                "description": description,
                "version": "1.0.0",
                "tools": [],
                "keywords": keywords,
                "created_at": _now(),
            }
            (domain_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            # Generate SKILL.md
            self._write_skill_md(domain_dir, name, description, [])

            self._domains[domain_id] = manifest
            return manifest

    def add_tool_to_domain(
        self, domain_id: str, tool_id: str, name: str, description: str,
        contract: dict[str, Any], handler_code: str,
    ) -> dict[str, Any]:
        """Add a tool to an existing domain."""
        with self._lock:
            domain_dir = self._dir / domain_id
            if not domain_dir.exists():
                raise KeyError(f"Domain '{domain_id}' not found")

            # Save contract
            contract_path = domain_dir / "contracts" / f"{tool_id}.json"
            contract_path.write_text(
                json.dumps(contract, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            # Save handler
            handler_path = domain_dir / "handlers" / f"{tool_id}.py"
            handler_path.write_text(handler_code, encoding="utf-8")

            # Update manifest
            manifest_path = domain_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else self._domains.get(domain_id, {})

            tools = manifest.get("tools", [])
            # Remove if already exists (update)
            tools = [t for t in tools if t.get("id") != tool_id]
            tools.append({"id": tool_id, "name": name, "description": description})
            manifest["tools"] = tools
            manifest["version"] = self._bump_version(manifest.get("version", "1.0.0"))

            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            # Regenerate SKILL.md
            self._write_skill_md(domain_dir, manifest["name"], manifest["description"], tools)

            self._domains[domain_id] = manifest
            return {"domain_id": domain_id, "tool_id": tool_id, "domain_tools": len(tools)}

    def list_domains(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {**d, "tool_count": len(d.get("tools", []))}
                for d in self._domains.values()
            ]

    def get_domain(self, domain_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._domains.get(domain_id)

    def _write_skill_md(self, domain_dir: Path, name: str, description: str, tools: list[dict]) -> None:
        """Generate SKILL.md for the domain."""
        tools_section = "\n".join(f"- `{t['id']}` — {t.get('description', '')}" for t in tools)
        md = f"""---
domain: {domain_dir.name}
name: {name}
description: {description}
---

# {name}

{description}

## Tools
{tools_section or "No tools yet."}
"""
        (domain_dir / "SKILL.md").write_text(md, encoding="utf-8")

    @staticmethod
    def _bump_version(version: str) -> str:
        parts = version.split(".")
        if len(parts) == 3:
            parts[2] = str(int(parts[2]) + 1)
        return ".".join(parts)

    def _load(self) -> None:
        with self._lock:
            for d in self._dir.iterdir():
                if d.is_dir():
                    manifest_path = d / "manifest.json"
                    if manifest_path.exists():
                        try:
                            self._domains[d.name] = json.loads(manifest_path.read_text(encoding="utf-8"))
                        except Exception:
                            pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
