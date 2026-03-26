from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from threading import RLock
from typing import Any


@dataclass
class SessionElementState:
    next_index: int = 1
    page_url: str | None = None
    snapshot_signature: str | None = None
    by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    by_dom_key: dict[str, str] = field(default_factory=dict)
    ordered_ids: list[str] = field(default_factory=list)


class ElementRegistry:
    """In-memory per-session registry for interactive elements inside worker."""

    def __init__(self):
        self._lock = RLock()
        self._sessions: dict[str, SessionElementState] = {}

    def reconcile(
        self,
        *,
        session_id: str,
        page_url: str | None,
        mapped_elements: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        with self._lock:
            state = self._sessions.setdefault(session_id, SessionElementState())
            if state.page_url is not None and page_url is not None and state.page_url != page_url:
                _reset_state(state)

            signature = _build_signature(mapped_elements)
            if signature == state.snapshot_signature and state.ordered_ids:
                return [self._public_element(state.by_id[element_id]) for element_id in state.ordered_ids if element_id in state.by_id]

            new_by_id: dict[str, dict[str, Any]] = {}
            new_by_dom_key: dict[str, str] = {}
            new_order: list[str] = []

            for item in mapped_elements:
                dom_key = item.get("_dom_key")
                if not isinstance(dom_key, str) or not dom_key:
                    continue
                existing_id = state.by_dom_key.get(dom_key)
                if existing_id is None:
                    existing_id = _new_element_id(state.next_index)
                    state.next_index += 1

                record = dict(item)
                record["element_id"] = existing_id
                new_by_id[existing_id] = record
                new_by_dom_key[dom_key] = existing_id
                new_order.append(existing_id)

            state.by_id = new_by_id
            state.by_dom_key = new_by_dom_key
            state.ordered_ids = new_order
            state.page_url = page_url
            state.snapshot_signature = signature
            return [self._public_element(state.by_id[element_id]) for element_id in state.ordered_ids if element_id in state.by_id]

    def get(self, *, session_id: str, element_id: str) -> dict[str, Any] | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            record = session.by_id.get(element_id)
            if record is None:
                return None
            return dict(record)

    def remove(self, *, session_id: str, element_id: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            record = session.by_id.pop(element_id, None)
            if record is None:
                return
            dom_key = record.get("_dom_key")
            if isinstance(dom_key, str):
                session.by_dom_key.pop(dom_key, None)
            if element_id in session.ordered_ids:
                session.ordered_ids = [eid for eid in session.ordered_ids if eid != element_id]

    def invalidate(self, *, session_id: str | None = None) -> None:
        with self._lock:
            if session_id is None:
                self._sessions = {}
                return
            self._sessions.pop(session_id, None)

    def _public_element(self, record: dict[str, Any]) -> dict[str, Any]:
        payload = dict(record)
        payload.pop("_dom_key", None)
        return payload


def _build_signature(elements: list[dict[str, Any]]) -> str:
    dom_keys: list[str] = []
    for element in elements:
        dom_key = element.get("_dom_key")
        if isinstance(dom_key, str) and dom_key:
            dom_keys.append(dom_key)
    serialized = json.dumps(dom_keys, ensure_ascii=True, sort_keys=False)
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()


def _new_element_id(index: int) -> str:
    return f"el_{index:03d}"


def _reset_state(state: SessionElementState) -> None:
    state.next_index = 1
    state.page_url = None
    state.snapshot_signature = None
    state.by_id = {}
    state.by_dom_key = {}
    state.ordered_ids = []
