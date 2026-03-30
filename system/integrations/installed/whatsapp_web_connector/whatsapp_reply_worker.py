"""WhatsApp auto-reply worker — listens for incoming messages and responds via LLM.

Subscribes to ``whatsapp_message`` events on the event bus (emitted by any
backend: Baileys, Browser/Puppeteer, or Official API webhook).

Routes each message through the same pipeline as Telegram/Slack/Discord:
  1. Authorization (allowed_user_ids)
  2. Sanitization (prompt injection detection)
  3. Classification (conversational vs action)
  4. Interpretation → Execution → Reply
"""
from __future__ import annotations

import json
import threading
import time
from collections import deque
from typing import Any

from system.integrations.channel_adapter import (
    ChannelAdapter,
    CHANNEL_BLOCKED_CAPABILITIES,
    CHANNEL_CONFIRM_REQUIRED,
    MAX_MESSAGE_LENGTH,
    _INJECTION_PATTERNS,
)


class WhatsAppReplyWorker:
    """Listens for whatsapp_message events and auto-replies via the active backend."""

    def __init__(
        self,
        backend_manager: Any,
        interpreter: Any = None,
        executor: Any = None,
        execution_history: Any = None,
        allowed_user_ids: list[str] | None = None,
        agent_loop: Any = None,
    ) -> None:
        self._manager = backend_manager
        self._interpreter = interpreter
        self._executor = executor
        self._history = execution_history
        self._agent_loop = agent_loop
        self._allowed_user_ids: list[str] = list(allowed_user_ids or [])
        self._running = False
        self._unsub: Any = None
        self._queue: deque[dict[str, Any]] = deque(maxlen=100)
        self._thread: threading.Thread | None = None
        self._pending: dict[str, dict[str, Any]] = {}
        self._chat_messages: dict[str, list[dict[str, Any]]] = {}

    @property
    def running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        from system.core.ui_bridge.event_bus import event_bus
        self._unsub = event_bus.subscribe(self._on_event)
        self._running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True, name="whatsapp-reply")
        self._thread.start()
        print("[WHATSAPP-REPLY] Worker started", flush=True)

    def stop(self) -> None:
        self._running = False
        if self._unsub:
            self._unsub()
            self._unsub = None

    def configure(self, allowed_user_ids: list[str] | None = None) -> None:
        if allowed_user_ids is not None:
            self._allowed_user_ids = list(allowed_user_ids)

    def get_status(self) -> dict[str, Any]:
        return {"running": self.running, "queue_size": len(self._queue)}

    # ------------------------------------------------------------------
    # Event bus listener
    # ------------------------------------------------------------------

    def _on_event(self, event: dict[str, Any]) -> None:
        if event.get("type") != "whatsapp_message":
            return
        data = event.get("data", {})
        if data.get("text"):
            self._queue.append(data)

    # ------------------------------------------------------------------
    # Processing loop
    # ------------------------------------------------------------------

    def _process_loop(self) -> None:
        while self._running:
            while self._queue:
                try:
                    msg = self._queue.popleft()
                    self._process_message(msg)
                except Exception as exc:
                    print(f"[WHATSAPP-REPLY] Error: {exc}", flush=True)
            time.sleep(1)
        print("[WHATSAPP-REPLY] Worker stopped", flush=True)

    def _process_message(self, msg: dict[str, Any]) -> None:
        from_id = msg.get("from", "")
        text = msg.get("text", "").strip()
        push_name = msg.get("pushName", from_id)

        if not text:
            return

        # Layer 1: Authorization
        if self._allowed_user_ids:
            # Check by JID, phone number, or push name
            authorized = False
            phone = from_id.split("@")[0] if "@" in from_id else from_id
            for allowed in self._allowed_user_ids:
                if allowed in (from_id, phone, push_name):
                    authorized = True
                    break
            if not authorized:
                print(f"[WHATSAPP-REPLY] Unauthorized: {from_id}", flush=True)
                return
        # If no allowed_user_ids configured, allow all (open mode)

        # Pending confirmation?
        if from_id in self._pending:
            self._handle_confirmation(from_id, text, push_name)
            return

        # Layer 2: Sanitization
        import re
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        cleaned = cleaned[:MAX_MESSAGE_LENGTH]
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(cleaned):
                self._reply(from_id, "No puedo procesar ese mensaje.")
                return

        # Emit to event bus for UI tracking
        try:
            from system.core.ui_bridge.event_bus import event_bus
            event_bus.emit("whatsapp_message_processed", {
                "from": from_id, "pushName": push_name, "text": text[:100],
            })
        except Exception:
            pass

        self._handle_message(from_id, cleaned, push_name)

    # ------------------------------------------------------------------
    # Message handling (mirrors ChannelPollingWorker)
    # ------------------------------------------------------------------

    def _handle_message(self, channel_id: str, text: str, user_name: str) -> None:
        # Use AgentLoop if available (autonomous mode)
        if self._agent_loop is not None:
            self._handle_message_agent(channel_id, text, user_name)
            return

        # Fallback: rigid interpret-then-execute
        if self._interpreter is None:
            self._reply(channel_id, "Sistema no listo.")
            return

        t0 = time.monotonic()
        try:
            msg_type = self._interpreter.classify_message(text)
            if msg_type == "conversational":
                response = self._interpreter.chat_response(text, user_name)
                self._reply(channel_id, response)
                self._record(text, response, t0, user_name, channel_id)
                return

            interpretation = self._interpreter.interpret(text)
            suggestion = interpretation.get("suggestion", {})
            if suggestion.get("type") == "unknown":
                self._reply(channel_id, "No entendi eso. Puedes ser mas especifico?")
                return

            steps: list[dict[str, Any]] = []
            if suggestion.get("type") == "capability":
                steps = [{"capability": suggestion.get("capability"), "inputs": suggestion.get("inputs", {})}]
            elif suggestion.get("type") == "sequence":
                steps = suggestion.get("steps", [])

            if not steps:
                self._reply(channel_id, "No pude crear un plan para eso.")
                return

            # Layer 3: Capability sandbox
            for step in steps:
                cap = step.get("capability", "")
                if cap in CHANNEL_BLOCKED_CAPABILITIES:
                    self._reply(channel_id, f"Esa accion ({cap}) no esta permitida desde WhatsApp.")
                    return
                if cap in CHANNEL_CONFIRM_REQUIRED:
                    self._pending[channel_id] = {"steps": steps, "expires": time.time() + 60}
                    inputs_str = json.dumps(step.get("inputs", {}), ensure_ascii=False)[:200]
                    self._reply(channel_id, f"Esta accion requiere confirmacion:\n{cap}\n{inputs_str}\n\nResponde si para confirmar o no para cancelar.")
                    return

            self._execute_steps(channel_id, steps, text, t0, user_name)

        except Exception as exc:
            self._reply(channel_id, f"Error: {str(exc)[:200]}")

    def _execute_steps(self, channel_id: str, steps: list[dict[str, Any]], original_text: str = "", t0: float = 0, user_name: str = "") -> None:
        if self._executor is None:
            self._reply(channel_id, "Executor no disponible.")
            return
        self._reply(channel_id, f"Ejecutando {len(steps)} paso(s)...")
        last_response = ""
        for step in steps:
            cap = step.get("capability", "")
            inputs = step.get("inputs", {})
            try:
                result = self._executor(cap, inputs)
                if result and result.get("status") == "success":
                    output = result.get("final_output", {})
                    formatted = self._format_output(cap, output)
                    self._reply(channel_id, formatted)
                    last_response = formatted
                else:
                    err = result.get("error_message", "Error desconocido") if result else "Sin resultado"
                    self._reply(channel_id, f"Error en {cap}: {err}")
                    return
            except Exception as exc:
                self._reply(channel_id, f"Error en {cap}: {str(exc)[:200]}")
                return
        if last_response:
            self._record(original_text, last_response, t0, user_name, channel_id)

    def _handle_confirmation(self, channel_id: str, text: str, user_name: str) -> None:
        pending = self._pending.get(channel_id)
        if not pending:
            return
        if time.time() > pending["expires"]:
            del self._pending[channel_id]
            self._reply(channel_id, "Confirmacion expirada. Repite el comando.")
            return
        lower = text.lower().strip()
        if lower in ("yes", "si", "y", "s"):
            del self._pending[channel_id]
            self._execute_steps(channel_id, pending["steps"])
        elif lower in ("no", "n", "cancel", "cancelar"):
            del self._pending[channel_id]
            self._reply(channel_id, "Accion cancelada.")
        else:
            self._reply(channel_id, "Responde si o no.")

    # ------------------------------------------------------------------
    # Reply
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Agent mode handler
    # ------------------------------------------------------------------

    def _handle_message_agent(self, channel_id: str, text: str, user_name: str) -> None:
        """Use the AgentLoop for autonomous processing."""
        t0 = time.monotonic()
        print(f"[WHATSAPP-REPLY] Agent processing: '{text[:50]}' from {user_name}", flush=True)
        try:
            final_text = ""
            gen = self._agent_loop.run(text)
            for event in gen:
                etype = event.get("event", "")
                if etype == "agent_response":
                    final_text = event.get("text", "")
                    print(f"[WHATSAPP-REPLY] Agent response: '{final_text[:80]}'", flush=True)
                elif etype == "tool_call":
                    print(f"[WHATSAPP-REPLY] Tool call: {event.get('tool_id')} (L{event.get('security_level')})", flush=True)
                elif etype == "awaiting_confirmation":
                    tool_id = event.get("tool_id", "")
                    self._reply(channel_id, f"La accion '{tool_id}' requiere confirmacion que solo se puede dar desde la interfaz web.")
                    return
                elif etype == "agent_error":
                    err = event.get("error", "")
                    print(f"[WHATSAPP-REPLY] Agent error: {err}", flush=True)
                    if "LLM" in err or "401" in err or "api_key" in err.lower():
                        self._reply(channel_id, "LLM no disponible en este momento. Intenta mas tarde.")
                        return

            if final_text:
                self._reply(channel_id, final_text)
                self._record(text, final_text, t0, user_name, channel_id)
            else:
                self._reply(channel_id, "No pude procesar eso. Intenta de otra forma.")

        except Exception as exc:
            print(f"[WHATSAPP-REPLY] Exception: {exc}", flush=True)
            self._reply(channel_id, f"Error del sistema. Intenta mas tarde.")

    def _reply(self, to: str, text: str) -> None:
        try:
            # Extract phone/name from JID for the backend
            contact = to.split("@")[0] if "@" in to else to
            self._manager.send_message(contact, (text or "...")[:4096])
        except Exception as exc:
            print(f"[WHATSAPP-REPLY] Send error: {exc}", flush=True)

    # ------------------------------------------------------------------
    # Formatting & Recording
    # ------------------------------------------------------------------

    @staticmethod
    def _format_output(cap: str, output: dict[str, Any]) -> str:
        if "items" in output:
            items = output["items"]
            lines = [f"{len(items)} items:"]
            for it in items[:20]:
                icon = "dir" if it.get("type") == "directory" else "file"
                lines.append(f"  {icon}  {it.get('name', '?')}")
            if len(items) > 20:
                lines.append(f"  ...y {len(items) - 20} mas")
            return "\n".join(lines)
        if "content" in output:
            return str(output["content"])[:3000]
        t = json.dumps(output, indent=2, ensure_ascii=False)
        return t[:3000] + ("\n...(truncado)" if len(t) > 3000 else "")

    def _record(self, intent: str, response: str, t0: float, user_name: str, channel_id: str = "") -> None:
        if self._history is None:
            return
        try:
            elapsed = int((time.monotonic() - t0) * 1000) if t0 else 0
            sid = f"whatsapp_{channel_id}" if channel_id else f"whatsapp_{int(time.time())}"
            if channel_id not in self._chat_messages:
                self._chat_messages[channel_id] = []
            buf = self._chat_messages[channel_id]
            buf.append({"role": "user", "content": intent, "type": "chat"})
            buf.append({"role": "assistant", "content": response[:500], "type": "chat"})
            if len(buf) > 20:
                self._chat_messages[channel_id] = buf[-20:]
                buf = self._chat_messages[channel_id]
            first_intent = ""
            for m in buf:
                if m["role"] == "user":
                    first_intent = m["content"][:100]
                    break
            self._history.upsert_chat(
                session_id=sid,
                intent=f"[WA @{user_name}] {first_intent or intent[:100]}",
                messages=list(buf),
                duration_ms=elapsed,
            )
            try:
                from system.core.ui_bridge.event_bus import event_bus
                event_bus.emit("session_updated", {"session_id": sid})
            except Exception:
                pass
        except Exception:
            pass
