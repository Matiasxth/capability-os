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
    ws_filter = None
    if _raw_path and "?" in _raw_path:
        qs = parse_qs(urlparse(_raw_path).query)
        cap_filter = qs.get("capability_id", [None])[0]
        ws_filter = qs.get("workspace_id", [None])[0]
    if ws_filter:
        entries = service.execution_history.get_by_workspace(ws_filter)
    elif cap_filter:
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
        workspace_id=body.get("workspace_id"),
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


# ------------------------------------------------------------------
# Markdown Memory endpoints
# ------------------------------------------------------------------

def get_markdown_memory(service: Any, payload: Any, **kw: Any):
    """Return MEMORY.md content and parsed sections."""
    md = getattr(service, "markdown_memory", None)
    if md is None:
        return _resp(HTTPStatus.OK, {"content": "", "sections": {}})
    content = md.load_memory_md()
    sections = md.load_memory_sections()
    # Clean section values
    clean_sections = {}
    for k, lines in sections.items():
        clean_sections[k] = [l.strip() for l in lines if l.strip()]
    return _resp(HTTPStatus.OK, {"content": content, "sections": clean_sections})


def save_markdown_memory(service: Any, payload: Any, **kw: Any):
    """Overwrite MEMORY.md with provided content."""
    md = getattr(service, "markdown_memory", None)
    if md is None:
        _err(HTTPStatus.SERVICE_UNAVAILABLE, "not_available", "Markdown memory not initialized.")
    body = payload or {}
    content = body.get("content", "")
    md.save_memory_md(content)
    return _resp(HTTPStatus.OK, {"status": "success"})


def add_memory_fact(service: Any, payload: Any, **kw: Any):
    """Add a fact to a section in MEMORY.md."""
    md = getattr(service, "markdown_memory", None)
    if md is None:
        _err(HTTPStatus.SERVICE_UNAVAILABLE, "not_available", "Markdown memory not initialized.")
    body = payload or {}
    section = body.get("section", "")
    fact = body.get("fact", "")
    if not section or not fact:
        _err(HTTPStatus.BAD_REQUEST, "missing_fields", "Fields 'section' and 'fact' are required.")
    md.add_fact(section, fact)
    return _resp(HTTPStatus.OK, {"status": "success"})


def remove_memory_fact(service: Any, payload: Any, **kw: Any):
    """Remove a fact from MEMORY.md."""
    md = getattr(service, "markdown_memory", None)
    if md is None:
        _err(HTTPStatus.SERVICE_UNAVAILABLE, "not_available", "Markdown memory not initialized.")
    body = payload or {}
    section = body.get("section", "")
    fact_substring = body.get("fact_substring", "")
    if not section or not fact_substring:
        _err(HTTPStatus.BAD_REQUEST, "missing_fields", "Fields 'section' and 'fact_substring' are required.")
    removed = md.remove_fact(section, fact_substring)
    return _resp(HTTPStatus.OK, {"status": "success", "removed": removed})


def get_daily_notes(service: Any, payload: Any, _raw_path: str = "", **kw: Any):
    """Return daily notes list and optionally a specific date's content."""
    md = getattr(service, "markdown_memory", None)
    if md is None:
        return _resp(HTTPStatus.OK, {"dates": [], "content": ""})
    qs = parse_qs(urlparse(_raw_path).query) if _raw_path else {}
    date_str = (qs.get("date") or [""])[0]
    dates = md.list_daily_dates(limit=14)
    content = ""
    if date_str:
        from datetime import datetime, timezone
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            content = md.load_daily(dt)
        except ValueError:
            pass
    elif dates:
        from datetime import datetime, timezone
        try:
            dt = datetime.strptime(dates[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            content = md.load_daily(dt)
        except ValueError:
            pass
    return _resp(HTTPStatus.OK, {"dates": dates, "content": content})


def get_session_summaries(service: Any, payload: Any, **kw: Any):
    """Return list of compacted session summaries."""
    md = getattr(service, "markdown_memory", None)
    if md is None:
        return _resp(HTTPStatus.OK, {"sessions": []})
    session_ids = md.list_sessions(limit=20)
    sessions = []
    for sid in session_ids:
        summary = md.load_session_summary(sid)
        sessions.append({"session_id": sid, "summary": summary[:200] if summary else ""})
    return _resp(HTTPStatus.OK, {"sessions": sessions})


def get_memory_agent_context(service: Any, payload: Any, **kw: Any):
    """Return the compact memory context that gets injected into agent prompts."""
    md = getattr(service, "markdown_memory", None)
    if md is None:
        return _resp(HTTPStatus.OK, {"context": ""})
    context = md.build_context(max_tokens=500)
    return _resp(HTTPStatus.OK, {"context": context})
