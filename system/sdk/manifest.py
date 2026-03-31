"""Plugin manifest — declarative metadata for discovery and loading."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str
    description: str = ""
    author: str = "CapabilityOS"
    plugin_types: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    entry_point: str = "plugin:create_plugin"
    settings_key: str = ""
    auto_start: bool = True
    sdk_min_version: str = ""

    # v2 — permissions & capabilities
    permissions: list[str] = field(default_factory=list)
    required_services: list[str] = field(default_factory=list)
    provided_services: list[str] = field(default_factory=list)
    events_emitted: list[str] = field(default_factory=list)
    events_consumed: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)

    # v2 — marketplace metadata
    license: str = ""
    homepage: str = ""
    tags: list[str] = field(default_factory=list)
    optional_dependencies: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginManifest:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_file(cls, path: Path) -> PluginManifest:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)
