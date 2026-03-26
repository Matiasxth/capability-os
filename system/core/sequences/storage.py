from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


class SequenceStorageError(RuntimeError):
    """Raised when sequence storage operations fail."""


_SEQUENCE_ID_PATTERN = re.compile(r"^[a-z]+(?:_[a-z0-9]+)*$")


class SequenceStorage:
    """Stores sequence JSON definitions inside workspace/sequences."""

    def __init__(self, workspace_root: str | Path, sequences_path: str | Path | None = None):
        self.workspace_root = Path(workspace_root).resolve()
        default_dir = (self.workspace_root / "sequences").resolve()
        self.sequences_dir = self._resolve_sequences_dir(sequences_path or default_dir)
        self.sequences_dir.mkdir(parents=True, exist_ok=True)

    def save(self, sequence_id: str, definition: dict[str, Any], *, overwrite: bool = False) -> Path:
        path = self._path_for(sequence_id)
        if path.exists() and not overwrite:
            raise SequenceStorageError(f"Sequence '{sequence_id}' already exists.")

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(definition, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def load(self, sequence_id: str) -> dict[str, Any]:
        path = self._path_for(sequence_id)
        if not path.exists() or not path.is_file():
            raise SequenceStorageError(f"Sequence '{sequence_id}' does not exist.")

        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise SequenceStorageError(
                f"Sequence '{sequence_id}' contains invalid JSON."
            ) from exc

    def list_ids(self) -> list[str]:
        ids: list[str] = []
        for item in sorted(self.sequences_dir.glob("*.json")):
            ids.append(item.stem)
        return ids

    def _path_for(self, sequence_id: str) -> Path:
        if not isinstance(sequence_id, str) or not _SEQUENCE_ID_PATTERN.match(sequence_id):
            raise SequenceStorageError(
                "Sequence id must be snake_case (e.g. 'daily_build_sequence')."
            )

        path = (self.sequences_dir / f"{sequence_id}.json").resolve()
        try:
            common = os.path.commonpath([str(self.sequences_dir), str(path)])
        except ValueError as exc:
            raise SequenceStorageError("Sequence path is outside workspace.") from exc

        if Path(common) != self.sequences_dir:
            raise SequenceStorageError("Sequence path is outside workspace.")
        return path

    def configure_sequences_path(self, sequences_path: str | Path) -> None:
        resolved = self._resolve_sequences_dir(sequences_path)
        self.sequences_dir = resolved
        self.sequences_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_sequences_dir(self, value: str | Path) -> Path:
        raw = Path(value)
        candidate = raw if raw.is_absolute() else (self.workspace_root / raw)
        resolved = candidate.resolve()
        try:
            common = os.path.commonpath([str(self.workspace_root), str(resolved)])
        except ValueError as exc:
            raise SequenceStorageError("Sequence storage path is outside workspace.") from exc
        if Path(common) != self.workspace_root:
            raise SequenceStorageError("Sequence storage path is outside workspace.")
        return resolved
