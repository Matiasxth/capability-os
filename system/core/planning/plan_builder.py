from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


class PlanBuildError(ValueError):
    """Raised when interpreted intent cannot be converted into a plan."""


class PlanBuilder:
    """Converts intent interpreter output into a normalized execution plan."""

    def build(self, interpretation: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(interpretation, dict):
            raise PlanBuildError("Interpretation payload must be an object.")

        suggestion = interpretation.get("suggestion", {})
        if not isinstance(suggestion, dict):
            raise PlanBuildError("Interpretation field 'suggestion' must be an object.")

        suggestion_type = suggestion.get("type")
        if suggestion_type not in {"capability", "sequence", "unknown"}:
            raise PlanBuildError("Suggestion field 'type' must be capability, sequence, or unknown.")

        suggest_only = interpretation.get("suggest_only", True)
        if not isinstance(suggest_only, bool):
            suggest_only = True

        if suggestion_type == "unknown":
            return {
                "type": "unknown",
                "suggest_only": suggest_only,
                "steps": [],
            }

        if suggestion_type == "capability":
            capability_id = suggestion.get("capability")
            if not isinstance(capability_id, str) or not capability_id.strip():
                raise PlanBuildError("Capability suggestion requires non-empty 'capability'.")
            inputs = suggestion.get("inputs", {})
            if inputs is None:
                inputs = {}
            if not isinstance(inputs, dict):
                raise PlanBuildError("Capability suggestion field 'inputs' must be an object.")
            return {
                "type": "capability",
                "suggest_only": suggest_only,
                "steps": [
                    {
                        "step_id": "step_1",
                        "capability": capability_id.strip(),
                        "inputs": deepcopy(inputs),
                    }
                ],
            }

        raw_steps = suggestion.get("steps", [])
        if not isinstance(raw_steps, list):
            raise PlanBuildError("Sequence suggestion field 'steps' must be a list.")

        normalized_steps: list[dict[str, Any]] = []
        for index, raw_step in enumerate(raw_steps):
            if not isinstance(raw_step, dict):
                raise PlanBuildError("Each sequence step must be an object.")

            raw_step_id = raw_step.get("step_id")
            if isinstance(raw_step_id, str) and raw_step_id.strip():
                step_id = raw_step_id.strip()
            else:
                step_id = f"step_{index + 1}"

            capability_id = raw_step.get("capability")
            if not isinstance(capability_id, str) or not capability_id.strip():
                raise PlanBuildError(f"Step '{step_id}' requires non-empty 'capability'.")

            inputs = raw_step.get("inputs", {})
            if inputs is None:
                inputs = {}
            if not isinstance(inputs, dict):
                raise PlanBuildError(f"Step '{step_id}' field 'inputs' must be an object.")

            normalized_steps.append(
                {
                    "step_id": step_id,
                    "capability": capability_id.strip(),
                    "inputs": deepcopy(inputs),
                }
            )

        cleaned = _deduplicate_steps(normalized_steps)
        cleaned = _filter_phantom_reads(cleaned)
        cleaned = _filter_redundant_reads(cleaned)
        return {
            "type": "sequence",
            "suggest_only": suggest_only,
            "steps": cleaned,
        }


def _deduplicate_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove steps with identical capability + inputs, keeping the first."""
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, Any]] = []
    for step in steps:
        key = (
            step.get("capability", ""),
            str(sorted(step.get("inputs", {}).items())),
        )
        if key not in seen:
            seen.add(key)
            unique.append(step)
    return unique


_PHANTOM_PATTERNS = (
    "output.txt", "result.txt", "results.txt", "temp.txt",
    "list_directory_output", "_output.txt", "_result.txt",
)


def _filter_phantom_reads(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove read_file steps that reference invented output/temp files."""
    filtered: list[dict[str, Any]] = []
    for step in steps:
        cap = step.get("capability", "")
        if cap == "read_file":
            path = str(step.get("inputs", {}).get("path", "")).lower()
            if any(p in path for p in _PHANTOM_PATTERNS):
                continue  # Invented filename — skip
        filtered.append(step)
    return filtered


def _filter_redundant_reads(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove read_file steps that follow a list_directory on the same directory.

    The LLM sometimes adds a read_file after list_directory thinking it needs
    to "read" the directory output. list_directory already returns its results
    directly, so the read_file is redundant.
    """
    listed_dirs: set[str] = set()
    filtered: list[dict[str, Any]] = []
    for step in steps:
        cap = step.get("capability", "")
        inputs = step.get("inputs", {})
        if cap == "list_directory":
            dir_path = str(inputs.get("path", ""))
            if dir_path:
                listed_dirs.add(dir_path.rstrip("/\\").lower())
            filtered.append(step)
        elif cap == "read_file" and listed_dirs:
            file_path = str(inputs.get("path", ""))
            # Check if this file's parent was just listed
            parent = str(Path(file_path).parent).rstrip("/\\").lower() if file_path else ""
            file_lower = file_path.lower()
            # Skip if reading a file in a directory we just listed AND the
            # filename looks auto-generated (not explicitly user-requested)
            if parent in listed_dirs and _looks_auto_generated(file_lower):
                continue
            filtered.append(step)
        else:
            filtered.append(step)
    return filtered


def _looks_auto_generated(path_lower: str) -> bool:
    """Heuristic: filenames the LLM commonly invents after list_directory."""
    name = path_lower.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return name in (
        "readme.md", "readme.txt", "readme",
        "output.txt", "result.txt", "results.txt",
        "index.html", "index.js", "main.py",
    )
