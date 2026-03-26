from __future__ import annotations

from pathlib import Path

from system.shared.base_registry import BaseRegistry


class ToolRegistry(BaseRegistry):
    """Registry for tool contracts."""

    def __init__(self, schema_path: str | Path | None = None):
        default_schema = Path(__file__).resolve().parents[1] / "contracts" / "tool_contract.schema.json"
        super().__init__(schema_path or default_schema)
