"""Memory route handlers: history, sessions, preferences, semantic, metrics."""
from __future__ import annotations

from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs, urlparse


def _resp(code, data):
    from system.core.ui_bridge.api_server import APIResponse
    return APIResponse(code, data)


def _err(code, error_code, msg):
    from system.core.ui_bridge.api_server import APIRequestError
    raise APIRequestError(code, error_code, msg)


def get_metrics(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, {"metrics": service.metrics_collector.get_metrics()})


def get_context(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, {"context": service.user_context.get_context()})


def get_history(service: Any, payload: Any, _raw_path: str = "", **kw: Any):
    cap_filter = None
    if _raw_path and "?" in _raw_path:
        qs = parse_qs(urlparse(_raw_path).query)
        cap_filter = qs.get("capability_id", [None])[0]
    if cap_filter:
        entries = service.execution_history.get_by_capability(cap_filter)
    else:
        entries = service.execution_history.get_recent(20)
    return _resp(HTTPStatus.OK, {"history": entries})


def save_chat(service: Any, payload: Any, **kw: Any):
    body = payload or {}
    session_id = body.get("session_id", "")
    if not session_id:
        from datetime import datetime, timezone
        session_id = f"chat_{datetime.now(timezone.utc).isoformat().replace(':', '-')}"
    exec_id = service.execution_history.upsert_chat(
        session_id=session_id,
        intent=body.get("intent", ""),
        messages=body.get("messages"),
        duration_ms=body.get("duration_ms", 0),
    )
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("session_updated", {"session_id": exec_id or session_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, {"status": "success", "id": exec_id})


def delete_history(service: Any, payload: Any, exec_id: str = "", **kw: Any):
    deleted = service.execution_history.delete(exec_id)
    if not deleted:
        _err(HTTPStatus.NOT_FOUND, "entry_not_found", f"History entry '{exec_id}' not found.")
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("session_updated", {"session_id": exec_id, "action": "deleted"})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, {"status": "success", "deleted": exec_id})


def save_session(service: Any, payload: Any, **kw: Any):
    body = payload or {}
    exec_id = service.execution_history.record_session(
        intent=body.get("intent", ""),
        plan_steps=body.get("plan_steps", []),
        step_runs=body.get("step_runs", []),
        status=body.get("status", "unknown"),
        duration_ms=body.get("duration_ms", 0),
        error_message=body.get("error_message"),
        failed_step=body.get("failed_step"),
        final_output=body.get("final_output", {}),
    )
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("session_updated", {"session_id": exec_id})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, {"status": "success", "id": exec_id})


def get_session(service: Any, payload: Any, exec_id: str = "", **kw: Any):
    entry = service.execution_history.get_session(exec_id)
    if entry is None:
        _err(HTTPStatus.NOT_FOUND, "session_not_found", f"Session '{exec_id}' not found.")
    return _resp(HTTPStatus.OK, {"session": entry})


def get_preferences(service: Any, payload: Any, **kw: Any):
    return _resp(HTTPStatus.OK, {"preferences": service.user_context.get_context().get("custom_preferences", {})})


def set_preferences(service: Any, payload: Any, **kw: Any):
    prefs = (payload or {}).get("preferences", payload or {})
    if isinstance(prefs, dict):
        for k, v in prefs.items():
            service.user_context.set_preference(k, v)
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("preferences_updated", {"keys": list(prefs.keys()) if isinstance(prefs, dict) else []})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, {"status": "success", "preferences": service.user_context.get_context().get("custom_preferences", {})})


def search_semantic(service: Any, payload: Any, _raw_path: str = "", **kw: Any):
    qs = parse_qs(urlparse(_raw_path).query) if _raw_path else {}
    q = (qs.get("q") or qs.get("query") or [""])[0]
    top_k = int((qs.get("top_k") or ["5"])[0])
    results = service.semantic_memory.recall_semantic(q, top_k=top_k) if q else []
    return _resp(HTTPStatus.OK, {"results": results, "query": q, "count": len(results)})


def add_semantic(service: Any, payload: Any, **kw: Any):
    text = (payload or {}).get("text", "")
    if not isinstance(text, str) or not text.strip():
        _err(HTTPStatus.BAD_REQUEST, "missing_text", "Field 'text' is required.")
    mem_type = (payload or {}).get("memory_type", "capability_context")
    meta = (payload or {}).get("metadata", {})
    rec = service.semantic_memory.remember_semantic(text, metadata=meta, memory_type=mem_type)
    return _resp(HTTPStatus.OK, {"status": "success", "memory": rec})


def delete_semantic(service: Any, payload: Any, mem_id: str = "", **kw: Any):
    deleted = service.semantic_memory.forget_semantic(mem_id)
    if not deleted:
        _err(HTTPStatus.NOT_FOUND, "memory_not_found", f"Semantic memory '{mem_id}' not found.")
    return _resp(HTTPStatus.OK, {"status": "success", "deleted": mem_id})


def clear_all(service: Any, payload: Any, **kw: Any):
    service.execution_history.clear()
    service.vector_store.clear()
    for rec in service.memory_manager.recall_all():
        service.memory_manager.forget(rec["id"])
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("memory_cleared", {})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, {"status": "success", "message": "All memory cleared."})


def compact_sessions(service: Any, payload: Any, **kw: Any):
    body = payload or {}
    max_age_hours = body.get("max_age_hours", 24)
    compactable = service.execution_history.get_compactable_sessions(max_age_hours=max_age_hours)
    if not compactable:
        return _resp(HTTPStatus.OK, {"status": "success", "compacted": 0, "freed_messages": 0})
    compacted = 0
    freed = 0
    for entry in compactable:
        eid = entry.get("execution_id", "")
        msgs = entry.get("chat_messages", [])
        # Build summarization prompt
        conversation = "\n".join(f"{m.get('role','?')}: {m.get('content','')}" for m in msgs[:20])
        try:
            summary = service.intent_interpreter.llm_client.complete(
                system_prompt="Summarize this conversation in 2-3 concise sentences. Capture the key intent, actions taken, and outcome.",
                user_prompt=conversation,
            )
            if service.execution_history.compact_session(eid, summary):
                compacted += 1
                freed += len(msgs) - 1
        except Exception:
            continue
    try:
        from system.core.ui_bridge.event_bus import event_bus
        event_bus.emit("session_updated", {"action": "compacted", "count": compacted})
    except Exception:
        pass
    return _resp(HTTPStatus.OK, {"status": "success", "compacted": compacted, "freed_messages": freed})
