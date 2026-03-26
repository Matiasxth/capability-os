from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class SchemaValidationError(ValueError):
    """Raised when a JSON document fails schema validation."""


class DuplicateIdError(ValueError):
    """Raised when a registry receives two contracts with the same id."""


def load_json_file(path: str | Path) -> Any:
    """Load and parse a JSON file."""
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_schema(path: str | Path) -> dict[str, Any]:
    """Load a schema and enforce object root type."""
    schema = load_json_file(path)
    if not isinstance(schema, dict):
        raise SchemaValidationError(f"Schema at '{path}' must be a JSON object.")
    return schema


def validate_instance(instance: Any, schema: dict[str, Any], *, context: str = "instance") -> None:
    """Validate an instance against a subset of JSON Schema keywords used by this project."""
    _validate(instance, schema, schema, context)


def _resolve_ref(root_schema: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise SchemaValidationError(f"Unsupported $ref '{ref}'. Only local refs are allowed.")

    node: Any = root_schema
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            raise SchemaValidationError(f"Unresolvable $ref '{ref}'.")
        node = node[part]

    if not isinstance(node, dict):
        raise SchemaValidationError(f"Resolved $ref '{ref}' is not an object schema.")
    return node


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    raise SchemaValidationError(f"Unsupported schema type '{expected}'.")


def _validate(value: Any, schema_node: dict[str, Any], root_schema: dict[str, Any], path: str) -> None:
    if "$ref" in schema_node:
        resolved = _resolve_ref(root_schema, schema_node["$ref"])
        _validate(value, resolved, root_schema, path)
        return

    if "enum" in schema_node and value not in schema_node["enum"]:
        raise SchemaValidationError(f"{path}: value '{value}' not in enum {schema_node['enum']}.")

    expected_type = schema_node.get("type")
    if expected_type is not None:
        if isinstance(expected_type, list):
            if not any(_type_ok(value, item_type) for item_type in expected_type):
                raise SchemaValidationError(f"{path}: value has invalid type.")
        else:
            if not _type_ok(value, expected_type):
                raise SchemaValidationError(
                    f"{path}: expected type '{expected_type}', got '{type(value).__name__}'."
                )

    if isinstance(value, str):
        min_length = schema_node.get("minLength")
        if min_length is not None and len(value) < min_length:
            raise SchemaValidationError(f"{path}: string shorter than minLength={min_length}.")

        pattern = schema_node.get("pattern")
        if pattern is not None and re.match(pattern, value) is None:
            raise SchemaValidationError(f"{path}: string '{value}' does not match pattern '{pattern}'.")

    if isinstance(value, int) and not isinstance(value, bool):
        minimum = schema_node.get("minimum")
        if minimum is not None and value < minimum:
            raise SchemaValidationError(f"{path}: integer smaller than minimum={minimum}.")

    if isinstance(value, list):
        min_items = schema_node.get("minItems")
        if min_items is not None and len(value) < min_items:
            raise SchemaValidationError(f"{path}: array has fewer than {min_items} items.")

        items_schema = schema_node.get("items")
        if isinstance(items_schema, dict):
            for index, item in enumerate(value):
                _validate(item, items_schema, root_schema, f"{path}[{index}]")

    if isinstance(value, dict):
        min_properties = schema_node.get("minProperties")
        if min_properties is not None and len(value) < min_properties:
            raise SchemaValidationError(f"{path}: object has fewer than {min_properties} properties.")

        required = schema_node.get("required", [])
        for key in required:
            if key not in value:
                raise SchemaValidationError(f"{path}: missing required property '{key}'.")

        properties = schema_node.get("properties", {})
        additional = schema_node.get("additionalProperties", True)

        for key, item in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in properties:
                _validate(item, properties[key], root_schema, child_path)
            else:
                if additional is False:
                    raise SchemaValidationError(f"{path}: additional property '{key}' is not allowed.")
                if isinstance(additional, dict):
                    _validate(item, additional, root_schema, child_path)

