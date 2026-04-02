"""Persistent execution history that survives process restarts.

Stores a compact summary of each execution in
``workspace/memory/history.json`` for cross-session recall.

Rule 5: recording never blocks — all writes are wrapped in try/except.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any


_DEFAULT_MAX_ENTRIES = 500


class ExecutionHistory:
    """Thread-safe persistent execution history."""

    def __init__(self, data_path: str | Path, max_entries: int = _DEFAULT_MAX_ENTRIES, db: Any = None):
        self._path = Path(data_path).resolve()
        self._max = max(1, int(max_entries))
        self._lock = RLock()
        self._entries: list[dict[str, Any]] = []
        self._repo: Any = None
        if db is not None:
            try:
                from system.infrastructure.repositories import ExecutionRepository
                self._repo = ExecutionRepository(db)
            except Exception:
                pass
        self._load()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def record(self, runtime_model: dict[str, Any], intent: str | None = None) -> None:
        """Extract a compact summary from a finished runtime model and persist it.

        Must never raise.
        """
        try:
            entry = self._extract(runtime_model, intent)
            with self._lock:
                self._entries.insert(0, entry)
                if len(self._entries) > self._max:
                    self._entries = self._entries[:self._max]
                self._save()
        except Exception:
            pass  # Rule 5

    def record_session(
        self,
        intent: str,
        plan_steps: list[dict[str, Any]],
        step_runs: list[dict[str, Any]],
        status: str,
        duration_ms: int,
        error_message: str | None = None,
        failed_step: str | None = None,
        final_output: dict[str, Any] | None = None,
    ) -> str | None:
        """Record a full multi-step session. Returns execution_id or None."""
        try:
            entry = {
                "execution_id": f"session_{_now_iso().replace(':', '-')}",
                "capability_id": "multi_step_session",
                "intent": intent,
                "status": status,
                "duration_ms": duration_ms,
                "timestamp": _now_iso(),
                "error_code": None,
                "failed_step": failed_step,
                "key_outputs": _scalar_outputs(final_output or {}),
                "plan_steps": plan_steps,
                "step_runs": _compact_step_runs(step_runs),
                "error_message": error_message,
            }
            with self._lock:
                self._entries.insert(0, entry)
                if len(self._entries) > self._max:
                    self._entries = self._entries[: self._max]
                self._save()
            return entry["execution_id"]
        except Exception:
            return None  # Rule 5

    def upsert_chat(
        self,
        session_id: str,
        intent: str,
        messages: list[dict[str, Any]] | None = None,
        duration_ms: int = 0,
        workspace_id: str | None = None,
    ) -> str | None:
        """Create or update a session (chat, execution, or mixed). Returns the execution_id."""
        try:
            chat_msgs = messages or []
            compact = []
            has_execution = False
            last_status = "success"
            for m in chat_msgs[-20:]:
                c = str(m.get("content", ""))
                entry_data: dict[str, Any] = {"role": m.get("role", "user"), "content": c[:300]}
                msg_type = m.get("type")
                if msg_type:
                    entry_data["type"] = msg_type
                if msg_type == "execution":
                    has_execution = True
                    ex = m.get("execution")
                    if isinstance(ex, dict):
                        entry_data["execution"] = ex
                        last_status = ex.get("status", "success")
                elif msg_type == "plan":
                    pl = m.get("plan")
                    if isinstance(pl, dict):
                        entry_data["plan"] = pl
                compact.append(entry_data)
            last_resp = ""
            if compact:
                for m in reversed(compact):
                    if m["role"] in ("system", "assistant"):
                        last_resp = m["content"]
                        break
            with self._lock:
                # Try to find existing entry with this session_id
                existing = None
                for e in self._entries:
                    if e.get("execution_id") == session_id:
                        existing = e
                        break
                cap_id = "session" if has_execution else "chat"
                if existing is not None:
                    # Update in place
                    existing["intent"] = intent
                    existing["capability_id"] = cap_id
                    existing["status"] = last_status
                    existing["chat_messages"] = compact
                    existing["chat_response"] = last_resp
                    existing["message_count"] = len(compact)
                    existing["has_execution"] = has_execution
                    existing["key_outputs"] = {"response": last_resp[:200]}
                    existing["timestamp"] = _now_iso()
                    existing["duration_ms"] = duration_ms
                    if workspace_id:
                        existing["workspace_id"] = workspace_id
                else:
                    # Create new
                    entry = {
                        "execution_id": session_id,
                        "capability_id": cap_id,
                        "intent": intent,
                        "status": last_status,
                        "duration_ms": duration_ms,
                        "timestamp": _now_iso(),
                        "error_code": None,
                        "failed_step": None,
                        "has_execution": has_execution,
                        "key_outputs": {"response": last_resp[:200]},
                        "chat_messages": compact,
                        "chat_response": last_resp,
                        "message_count": len(compact),
                        "workspace_id": workspace_id,
                    }
                    self._entries.insert(0, entry)
                    if len(self._entries) > self._max:
                        self._entries = self._entries[: self._max]
                self._save()
            return session_id
        except Exception:
            return None  # Rule 5

    def get_session(self, execution_id: str) -> dict[str, Any] | None:
        """Return a single history entry by execution_id."""
        with self._lock:
            for e in self._entries:
                if e.get("execution_id") == execution_id:
                    return deepcopy(e)
        return None

    def delete(self, execution_id: str) -> bool:
        """Remove an entry by execution_id. Returns True if removed."""
        with self._lock:
            before = len(self._entries)
            self._entries = [e for e in self._entries if e.get("execution_id") != execution_id]
            if len(self._entries) < before:
                self._save()
                return True
        return False

    def clear(self) -> None:
        """Remove all entries."""
        with self._lock:
            self._entries = []
            self._save()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_recent(self, n: int = 20) -> list[dict[str, Any]]:
        """Return the N most recent entries (newest first), deduplicated."""
        with self._lock:
            seen: set[str] = set()
            result: list[dict[str, Any]] = []
            for e in self._entries:
                eid = e.get("execution_id", "")
                # Dedup by id
                if eid and eid in seen:
                    continue
                # Dedup by intent+messages — same conversation saved under different IDs
                intent = e.get("intent", "")
                msg_count = e.get("message_count", 0)
                content_key = f"{intent}:{msg_count}"
                if content_key in seen and intent:
                    continue
                if eid:
                    seen.add(eid)
                if intent:
                    seen.add(content_key)
                result.append(deepcopy(e))
                if len(result) >= max(1, n):
                    break
            return result

    def get_by_capability(self, capability_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return entries for a specific capability."""
        with self._lock:
            results: list[dict[str, Any]] = []
            for e in self._entries:
                if e.get("capability_id") == capability_id:
                    results.append(deepcopy(e))
                    if len(results) >= limit:
                        break
            return results

    def get_by_workspace(self, workspace_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Return entries for a specific workspace."""
        with self._lock:
            results: list[dict[str, Any]] = []
            for e in self._entries:
                if e.get("workspace_id") == workspace_id:
                    results.append(deepcopy(e))
                    if len(results) >= limit:
                        break
            return results

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Simple substring search on intent text."""
        q = query.lower()
        with self._lock:
            results: list[dict[str, Any]] = []
            for e in self._entries:
                intent = (e.get("intent") or "").lower()
                if q in intent:
                    results.append(deepcopy(e))
                    if len(results) >= limit:
                        break
            return results

    def get_stats(self) -> dict[str, Any]:
        """Aggregate success/failure counts by capability."""
        with self._lock:
            by_cap: dict[str, dict[str, int]] = {}
            for e in self._entries:
                cap = e.get("capability_id", "unknown")
                if cap not in by_cap:
                    by_cap[cap] = {"success": 0, "error": 0, "total": 0}
                by_cap[cap]["total"] += 1
                if e.get("status") in ("success", "ready"):
                    by_cap[cap]["success"] += 1
                else:
                    by_cap[cap]["error"] += 1
            return {
                "total_entries": len(self._entries),
                "by_capability": by_cap,
            }

    def count(self) -> int:
        with self._lock:
            return len(self._entries)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _extract(runtime_model: dict[str, Any], intent: str | None) -> dict[str, Any]:
        """Build a compact history entry from a runtime model."""
        fo = runtime_model.get("final_output", {})
        # Keep only scalar outputs to save space
        key_outputs: dict[str, Any] = {}
        if isinstance(fo, dict):
            for k, v in fo.items():
                if isinstance(v, (str, int, float, bool)) or v is None:
                    key_outputs[k] = v
                elif isinstance(v, str) and len(v) > 200:
                    key_outputs[k] = v[:200] + "..."

        return {
            "execution_id": runtime_model.get("execution_id", ""),
            "capability_id": runtime_model.get("capability_id", "unknown"),
            "intent": intent,
            "status": runtime_model.get("status", "unknown"),
            "duration_ms": runtime_model.get("duration_ms", 0),
            "timestamp": runtime_model.get("started_at") or _now_iso(),
            "error_code": runtime_model.get("error_code"),
            "failed_step": runtime_model.get("failed_step"),
            "key_outputs": key_outputs,
        }

    def _load(self) -> None:
        with self._lock:
            # Try DB first
            if self._repo is not None:
                try:
                    rows = self._repo.get_recent(self._max)
                    if rows:
                        self._entries = rows
                        return
                except Exception:
                    pass
            # Fallback: JSON file
            if not self._path.exists():
                self._entries = []
                return
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and isinstance(raw.get("history"), list):
                    self._entries = [e for e in raw["history"] if isinstance(e, dict)]
                else:
                    self._entries = []
                # Migrate JSON data into DB
                if self._repo is not None and self._entries:
                    for entry in self._entries:
                        try:
                            self._repo.insert(entry)
                        except Exception:
                            pass
            except (json.JSONDecodeError, OSError):
                self._entries = []

    def _save(self) -> None:
        # Write to DB if available
        if self._repo is not None:
            try:
                for entry in self._entries[:5]:  # only persist recent changes
                    self._repo.insert(entry)
            except Exception:
                pass
        # Always write JSON as backup
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"history": self._entries}
            self._path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except OSError:
            pass  # Rule 5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _scalar_outputs(fo: dict[str, Any]) -> dict[str, Any]:
    """Keep only scalar values from final_output to save space."""
    out: dict[str, Any] = {}
    if isinstance(fo, dict):
        for k, v in fo.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                out[k] = v[:200] + "..." if isinstance(v, str) and len(v) > 200 else v
    return out


def _compact_step_runs(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only essential fields from step_runs to save space."""
    compact: list[dict[str, Any]] = []
    for r in runs:
        compact.append({
            "step_id": r.get("step_id", ""),
            "capability": r.get("capability", ""),
            "status": r.get("status", "unknown"),
            "error_message": r.get("error_message"),
        })
    return compact
