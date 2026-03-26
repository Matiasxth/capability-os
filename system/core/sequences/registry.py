from __future__ import annotations

from typing import Any

from .model import SequenceDefinition, SequenceValidationError, parse_sequence_definition
from .storage import SequenceStorage


class SequenceRegistry:
    """Validates, saves and loads sequence definitions."""

    def __init__(self, storage: SequenceStorage):
        self.storage = storage

    def validate(self, sequence_definition: dict[str, Any]) -> SequenceDefinition:
        return parse_sequence_definition(sequence_definition)

    def save_sequence(self, sequence_definition: dict[str, Any], *, overwrite: bool = False) -> str:
        parsed = self.validate(sequence_definition)
        self.storage.save(parsed.sequence_id, parsed.to_dict(), overwrite=overwrite)
        return parsed.sequence_id

    def load_sequence(self, sequence_id: str) -> dict[str, Any]:
        definition = self.storage.load(sequence_id)
        parsed = self.validate(definition)
        return parsed.to_dict()

    def list_sequences(self) -> list[str]:
        return self.storage.list_ids()


__all__ = ["SequenceRegistry", "SequenceValidationError"]
