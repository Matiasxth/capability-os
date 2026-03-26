from __future__ import annotations

from pathlib import Path
from typing import Any

from .schema_validation import DuplicateIdError, SchemaValidationError, load_json_file, load_schema, validate_instance


class BaseRegistry:
    """Shared registry behavior for JSON-contract registries."""

    def __init__(self, schema_path: str | Path):
        self.schema_path = Path(schema_path)
        self.schema = load_schema(self.schema_path)
        self._items: dict[str, dict[str, Any]] = {}

    def load_from_directory(self, directory: str | Path) -> "BaseRegistry":
        contracts_dir = Path(directory)
        if not contracts_dir.exists():
            raise FileNotFoundError(f"Contracts directory '{contracts_dir}' does not exist.")

        for json_path in sorted(contracts_dir.glob("*.json")):
            document = load_json_file(json_path)
            self.register(document, source=str(json_path))

        return self

    def validate_contract(self, contract: dict[str, Any], *, source: str = "<memory>") -> str:
        validate_instance(contract, self.schema, context=source)
        self._post_schema_validation(contract, source)

        contract_id = contract.get("id")
        if not isinstance(contract_id, str) or not contract_id:
            raise SchemaValidationError(f"{source}: contract must include a non-empty string 'id'.")
        return contract_id

    def register(self, contract: dict[str, Any], *, source: str = "<memory>") -> None:
        contract_id = self.validate_contract(contract, source=source)

        if contract_id in self._items:
            raise DuplicateIdError(f"Duplicate id '{contract_id}' found in {source}.")

        self._items[contract_id] = contract

    def get(self, contract_id: str) -> dict[str, Any] | None:
        return self._items.get(contract_id)

    def list_all(self) -> list[dict[str, Any]]:
        return [self._items[key] for key in sorted(self._items)]

    def ids(self) -> list[str]:
        return sorted(self._items)

    def _post_schema_validation(self, contract: dict[str, Any], source: str) -> None:
        """Hook for specialized validations in subclasses."""

    def __len__(self) -> int:
        return len(self._items)
