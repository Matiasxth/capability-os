"""Agentic execution loop — the LLM iteratively calls tools, observes results, and decides next steps.

Unlike the old suggest-then-execute pipeline, this loop gives the LLM full
autonomy to call any registered tool, retry on errors, and explain results
to the user in natural language.

Security is enforced by the SecurityService which classifies every tool call
into Level 1 (free), Level 2 (confirm), or Level 3 (password).
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Generator

from .agent_state import AgentSession, PendingConfirmation
from .error_formatter import format_tool_error
from .prompts import build_agent_system_prompt
from .tool_use_adapter import AgentResponse, ToolUseAdapter, build_tool_definitions


def _dedup_text(text: str) -> str:
    """Remove repeated paragraphs that small LLMs sometimes generate."""
    if not text or len(text) < 50:
        return text
    # Split into paragraphs and remove exact duplicates
    paragraphs = text.split("\n\n")
    seen: list[str] = []
    for p in paragraphs:
        stripped = p.strip()
        if not stripped:
            continue
        if stripped not in seen:
            seen.append(stripped)
    result = "\n\n".join(seen)
    # Also detect repeated sentences within a single paragraph
    if result.count(". ") > 2:
        sentences = result.split(". ")
        deduped: list[str] = []
        for s in sentences:
            s = s.strip()
            if s and s not in deduped:
                deduped.append(s)
        result = ". ".join(deduped)
        if result and not result.endswith("."):
            result += "."
    return result


@dataclass
class AgentResult:
    session_id: str = ""
    status: str = "complete"  # complete | awaiting_confirmation | error | max_iterations
    final_text: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    iteration_count: int = 0


class AgentLoop:
    """Runs an iterative agent loop: LLM → tool call → result → LLM → ... """

    def __init__(
        self,
        tool_use_adapter: ToolUseAdapter,
        tool_runtime: Any,
        security_service: Any,
        tool_registry: Any,
        workspace_root: str = "",
        max_iterations: int = 10,
        execution_history: Any = None,
        markdown_memory: Any = None,
        memory_compactor: Any = None,
    ) -> None:
        self._adapter = tool_use_adapter
        self._tool_runtime = tool_runtime
        self._security = security_service
        self._tool_registry = tool_registry
        self._workspace_root = workspace_root
        self._max_iterations = max_iterations
        self._all_tools = build_tool_definitions(tool_registry)
        # Default tool set for when no agent config is provided
        priority_tools = {
            "filesystem_read_file", "filesystem_write_file", "filesystem_list_directory",
            "filesystem_create_directory", "filesystem_delete_file", "filesystem_copy_file",
            "filesystem_move_file", "filesystem_edit_file",
            "execution_run_command", "execution_run_script",
            "network_http_get", "network_extract_text",
            "browser_navigate", "browser_read_text", "browser_screenshot",
            "system_get_os_info", "system_get_workspace_info",
        }
        self._default_tools = [t for t in self._all_tools if t["name"] in priority_tools] or self._all_tools[:20]
        self._sessions: dict[str, AgentSession] = {}
        self._execution_history = execution_history
        self._markdown_memory = markdown_memory
        self._memory_compactor = memory_compactor
        self._redis_cache = None
        # Try to connect Redis cache for session persistence
        try:
            from system.infrastructure.message_queue import create_queue
            from system.infrastructure.redis_cache import RedisCache
            queue = create_queue({})
            self._redis_cache = RedisCache(queue)
        except Exception:
            pass

    def _resolve_tools(self, agent_config: dict[str, Any] | None) -> list[dict[str, Any]]:
        """Get the tool list for this agent. If agent has tool_ids, filter to those."""
        if agent_config and agent_config.get("tool_ids"):
            allowed = set(agent_config["tool_ids"])
            filtered = [t for t in self._all_tools if t["name"] in allowed]
            return filtered if filtered else self._default_tools
        return self._default_tools

    def get_session(self, session_id: str) -> AgentSession | None:
        session = self._sessions.get(session_id)
        if session is None and self._redis_cache:
            # Try Redis for cross-process session recovery
            data = self._redis_cache.get_session(session_id)
            if data:
                session = AgentSession(
                    session_id=data.get("session_id", session_id),
                    messages=data.get("messages", []),
                    status=data.get("status", "complete"),
                )
                self._sessions[session_id] = session
        return session

    def run(
        self,
        user_message: str,
        session_id: str | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
        agent_config: dict[str, Any] | None = None,
        workspace_id: str | None = None,
        workspace_path: str | None = None,
    ) -> Generator[dict[str, Any], None, AgentResult]:
        """Run the agent loop as a generator that yields events.

        Usage:
            gen = agent_loop.run("read my files")
            for event in gen:
                # stream event to frontend
                pass
            result = gen.value  # not accessible via for-loop, use send pattern
        """
        session = self._get_or_create_session(session_id, conversation_history)
        session.add_user_message(user_message)
        session.status = "running"

        # Auto-compact if context is too large
        self._try_compact(session)

        # Load memory context for prompt injection
        memory_ctx = ""
        if self._markdown_memory:
            try:
                memory_ctx = self._markdown_memory.build_context(max_tokens=500)
            except Exception:
                pass

        # Track workspace for this session
        session._workspace_id = workspace_id

        # Build prompt and tools based on agent config
        effective_ws = workspace_path or self._workspace_root
        system_prompt = build_agent_system_prompt(
            workspace_path=effective_ws,
            agent_config=agent_config,
            memory_context=memory_ctx,
        )
        tools = self._resolve_tools(agent_config)
        max_iter = (agent_config or {}).get("max_iterations") or self._max_iterations
        result = AgentResult(session_id=session.session_id)

        yield {"event": "agent_start", "session_id": session.session_id, "agent": (agent_config or {}).get("name", "CapOS")}

        for iteration in range(max_iter):
            session.iteration = iteration + 1

            yield {"event": "agent_thinking", "iteration": session.iteration}

            # Call LLM
            try:
                response = self._adapter.run_agent_turn(
                    messages=session.messages,
                    tools=tools,
                    system_prompt=system_prompt,
                )
            except Exception as exc:
                yield {"event": "agent_error", "error": f"LLM error: {exc}"}
                result.status = "error"
                result.final_text = f"Error calling LLM: {exc}"
                session.status = "error"
                return result

            # Handle text response (agent done)
            if response.stop_reason == "end_turn" or (response.text and not response.tool_calls):
                text = _dedup_text(response.text or "")
                session.add_assistant_message(text)
                session.final_text = text
                session.status = "complete"
                result.final_text = text
                result.status = "complete"
                result.iteration_count = session.iteration

                yield {"event": "agent_response", "text": text}
                self._auto_save(session, text)
                return result

            # Handle error from LLM
            if response.stop_reason == "error":
                text = response.text or "LLM error"
                session.add_assistant_message(text)
                yield {"event": "agent_error", "error": text}
                result.status = "error"
                result.final_text = text
                return result

            # Handle tool calls
            if response.tool_calls:
                # Store assistant message with tool calls
                session.add_assistant_message(
                    response.text or "",
                    tool_calls=[{"tool_id": tc.tool_id, "params": tc.params, "call_id": tc.call_id} for tc in response.tool_calls],
                )

                for tc in response.tool_calls:
                    call_id = tc.call_id or f"call_{uuid.uuid4().hex[:8]}"

                    # Security check
                    level = self._security.classify(
                        tool_id=tc.tool_id,
                        inputs=tc.params,
                    )

                    yield {
                        "event": "tool_call",
                        "tool_id": tc.tool_id,
                        "params": tc.params,
                        "security_level": int(level),
                        "call_id": call_id,
                    }

                    # Level 1: execute directly
                    if level.value == 1:
                        tool_result = self._execute_tool(tc.tool_id, tc.params)
                        session.add_tool_result(tc.tool_id, call_id, tool_result, success=tool_result.get("_success", True))

                        yield {
                            "event": "tool_result",
                            "tool_id": tc.tool_id,
                            "result": tool_result,
                            "success": tool_result.get("_success", True),
                            "call_id": call_id,
                        }

                    # Level 2/3: need confirmation
                    else:
                        confirmation = PendingConfirmation(
                            confirmation_id=f"conf_{uuid.uuid4().hex[:8]}",
                            tool_id=tc.tool_id,
                            params=tc.params,
                            security_level=int(level),
                            description=self._security.classify_description(level),
                        )
                        session.set_pending(confirmation)
                        result.status = "awaiting_confirmation"
                        result.iteration_count = session.iteration

                        yield {
                            "event": "awaiting_confirmation",
                            "confirmation_id": confirmation.confirmation_id,
                            "tool_id": tc.tool_id,
                            "params": tc.params,
                            "security_level": int(level),
                            "description": confirmation.description,
                        }
                        return result

        # Max iterations reached
        session.status = "complete"
        result.status = "max_iterations"
        result.final_text = "Reached maximum iterations. Please try a simpler request."
        result.iteration_count = self._max_iterations

        yield {"event": "agent_response", "text": result.final_text}
        return result

    def resume_after_confirmation(
        self,
        session_id: str,
        confirmation_id: str,
        approved: bool,
        agent_config: dict[str, Any] | None = None,
    ) -> Generator[dict[str, Any], None, AgentResult]:
        """Resume agent loop after user confirms/denies an action."""
        tools = self._resolve_tools(agent_config)
        session = self._sessions.get(session_id)
        if session is None:
            result = AgentResult(session_id=session_id, status="error", final_text="Session not found")
            yield {"event": "agent_error", "error": "Session not found"}
            return result

        conf = session.resolve_confirmation(confirmation_id, approved)
        if conf is None:
            result = AgentResult(session_id=session_id, status="error", final_text="Confirmation not found")
            yield {"event": "agent_error", "error": "Confirmation not found or expired"}
            return result

        if not approved:
            # User denied — tell the LLM
            session.add_tool_result(conf.tool_id, confirmation_id, {"denied": True, "message": "User denied this action"}, success=False)
            yield {"event": "tool_result", "tool_id": conf.tool_id, "result": {"denied": True}, "success": False, "call_id": confirmation_id}
        else:
            # User approved — execute the tool
            tool_result = self._execute_tool(conf.tool_id, conf.params)
            session.add_tool_result(conf.tool_id, confirmation_id, tool_result, success=tool_result.get("_success", True))
            yield {"event": "tool_result", "tool_id": conf.tool_id, "result": tool_result, "success": tool_result.get("_success", True), "call_id": confirmation_id}

        # Continue the loop
        system_prompt = build_agent_system_prompt(workspace_path=self._workspace_root)
        result = AgentResult(session_id=session.session_id)

        remaining = self._max_iterations - session.iteration
        for _ in range(max(1, remaining)):
            session.iteration += 1
            yield {"event": "agent_thinking", "iteration": session.iteration}

            try:
                response = self._adapter.run_agent_turn(
                    messages=session.messages,
                    tools=tools,
                    system_prompt=system_prompt,
                )
            except Exception as exc:
                result.status = "error"
                result.final_text = f"LLM error: {exc}"
                yield {"event": "agent_error", "error": str(exc)}
                return result

            if response.stop_reason == "end_turn" or (response.text and not response.tool_calls):
                text = _dedup_text(response.text or "")
                session.add_assistant_message(text)
                session.final_text = text
                session.status = "complete"
                result.final_text = text
                result.status = "complete"
                yield {"event": "agent_response", "text": text}
                return result

            if response.tool_calls:
                session.add_assistant_message(
                    response.text or "",
                    tool_calls=[{"tool_id": tc.tool_id, "params": tc.params, "call_id": tc.call_id} for tc in response.tool_calls],
                )
                for tc in response.tool_calls:
                    call_id = tc.call_id or f"call_{uuid.uuid4().hex[:8]}"
                    level = self._security.classify(tool_id=tc.tool_id, inputs=tc.params)

                    yield {"event": "tool_call", "tool_id": tc.tool_id, "params": tc.params, "security_level": int(level), "call_id": call_id}

                    if level.value == 1:
                        tool_result = self._execute_tool(tc.tool_id, tc.params)
                        session.add_tool_result(tc.tool_id, call_id, tool_result, success=tool_result.get("_success", True))
                        yield {"event": "tool_result", "tool_id": tc.tool_id, "result": tool_result, "success": tool_result.get("_success", True), "call_id": call_id}
                    else:
                        conf2 = PendingConfirmation(
                            confirmation_id=f"conf_{uuid.uuid4().hex[:8]}",
                            tool_id=tc.tool_id, params=tc.params,
                            security_level=int(level),
                            description=self._security.classify_description(level),
                        )
                        session.set_pending(conf2)
                        result.status = "awaiting_confirmation"
                        yield {"event": "awaiting_confirmation", "confirmation_id": conf2.confirmation_id, "tool_id": tc.tool_id, "params": tc.params, "security_level": int(level), "description": conf2.description}
                        return result

        result.status = "complete"
        result.final_text = "Task completed."
        yield {"event": "agent_response", "text": result.final_text}
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_or_create_session(
        self, session_id: str | None, history: list[dict[str, Any]] | None,
    ) -> AgentSession:
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        session = AgentSession(session_id=session_id)
        if history:
            for m in history:
                session.messages.append(m)
        self._sessions[session.session_id] = session
        # Persist to Redis for cross-process recovery
        if self._redis_cache:
            self._redis_cache.store_session(session.session_id, {
                "session_id": session.session_id,
                "messages": session.messages[-20:],
                "status": session.status,
            })
        # Prune old sessions (keep last 20)
        if len(self._sessions) > 20:
            oldest_key = next(iter(self._sessions))
            del self._sessions[oldest_key]
        return session

    def _auto_save(self, session: AgentSession, final_text: str) -> None:
        """Persist the session to execution history and daily notes."""
        if self._execution_history is None:
            return
        try:
            messages = session.to_persistable()
            first_user = ""
            for m in messages:
                if m.get("role") == "user":
                    first_user = m.get("content", "")[:100]
                    break
            self._execution_history.upsert_chat(
                session_id=session.session_id,
                intent=first_user or "Agent session",
                messages=messages,
                duration_ms=int((time.time() - session.created_at) * 1000),
                workspace_id=getattr(session, "_workspace_id", None),
            )
        except Exception:
            pass

        # Log to daily notes
        if self._markdown_memory and first_user:
            try:
                self._markdown_memory.append_daily(
                    f"{first_user[:80]}",
                    section="Sessions",
                )
            except Exception:
                pass

    def _try_compact(self, session: AgentSession) -> None:
        """Auto-compact session messages if they exceed the threshold."""
        if self._memory_compactor is None:
            return
        try:
            if not self._memory_compactor.should_compact(session.messages):
                return
            # Use LLM for summarization if available
            llm_fn = None
            try:
                llm_fn = lambda prompt: self._adapter._llm_client.complete(prompt)
            except Exception:
                pass
            result = self._memory_compactor.compact(
                messages=session.messages,
                llm_complete=llm_fn,
                session_id=session.session_id,
            )
            session.messages = result["compacted_messages"]
        except Exception:
            pass

    def _execute_tool(self, tool_id: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool via the ToolRuntime and return the result."""
        try:
            contract = self._tool_registry.get(tool_id)
            if contract is None:
                return {"_success": False, "error": f"Tool '{tool_id}' not found"}

            result = self._tool_runtime.execute(tool_id, params)
            if isinstance(result, dict):
                result["_success"] = result.get("status") != "error"
                return result
            return {"_success": True, "output": result}

        except Exception as exc:
            error_info = format_tool_error(tool_id, str(exc), params)
            return {
                "_success": False,
                "error": str(exc),
                **error_info,
            }
