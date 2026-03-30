"""Generic Channel Adapter pattern for messaging integrations.

Extracted from TelegramConnector/TelegramPollingWorker to enable
reuse across Slack, Discord, and future channels.

Three shared security layers:
  1. User whitelist (allowed_user_ids)
  2. Prompt-injection detection (regex blocklist)
  3. Capability sandboxing (blocked / confirm-required lists)
"""
from __future__ import annotations

import abc
import json
import re
import threading
import time
from typing import Any


# ── Shared security constants ──

CHANNEL_BLOCKED_CAPABILITIES = frozenset({
    "install_integration", "uninstall_integration",
    "approve_proposal", "reject_proposal",
    "update_settings", "system_settings",
})

CHANNEL_CONFIRM_REQUIRED = frozenset({
    "write_file", "filesystem_write_file",
    "delete_file", "filesystem_delete_file",
    "delete_directory", "filesystem_delete_directory",
    "move_file", "filesystem_move_file",
    "copy_file", "filesystem_copy_file",
    "execute_script", "execution_run_script",
    "execution_run_command",
})

_INJECTION_PATTERNS = [
    re.compile(r"ignor[ae]\s+(las?\s+)?(instrucciones|reglas|sistema)", re.I),
    re.compile(r"ignore\s+(all\s+|previous\s+|your\s+)?(instructions|rules)", re.I),
    re.compile(r"(eres ahora|you are now|act as|act[uú]a como)", re.I),
    re.compile(r"(system prompt|system:|<system>)", re.I),
    re.compile(r"(jailbreak|DAN|do anything now)", re.I),
    re.compile(r"(pretend you|finge que|imagina que eres)", re.I),
    re.compile(r"(override|bypass|circumvent)\s+(the\s+)?(rules|system|instructions)", re.I),
    re.compile(r"\[INST\]|\[SYS\]|<<SYS>>", re.I),
    re.compile(r"forget\s+(your\s+|all\s+)?instructions", re.I),
    re.compile(r"(nueva personalidad|new personality)", re.I),
]

MAX_MESSAGE_LENGTH = 2000


class ChannelError(RuntimeError):
    """Structured error for channel operations."""

    def __init__(self, message: str, error_code: str = "channel_error", details: dict[str, Any] | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


class ChannelAdapter(abc.ABC):
    """Abstract base for messaging channel connectors."""

    # Subclasses can extend these with channel-specific entries
    blocked_capabilities: frozenset[str] = CHANNEL_BLOCKED_CAPABILITIES
    confirm_required: frozenset[str] = CHANNEL_CONFIRM_REQUIRED

    def __init__(self, allowed_user_ids: list[str] | None = None):
        self._allowed_user_ids: list[str] = list(allowed_user_ids or [])

    @abc.abstractmethod
    def configure(self, **kwargs: Any) -> None:
        """Reconfigure the connector at runtime."""

    @abc.abstractmethod
    def validate(self) -> dict[str, Any]:
        """Validate credentials. Return {valid: bool, ...}."""

    @abc.abstractmethod
    def get_status(self) -> dict[str, Any]:
        """Return current status dict."""

    @abc.abstractmethod
    def send_message(self, channel_id: str, text: str, **kwargs: Any) -> dict[str, Any]:
        """Send a message to the channel. Return {status, message_id?, ...}."""

    # ── Shared security layers ──

    def is_authorized(self, user_id: str, username: str = "") -> tuple[bool, str]:
        """Layer 1: Check if user is in the allowed list."""
        if not self._allowed_user_ids:
            return False, "No authorized users configured"
        if str(user_id) in self._allowed_user_ids:
            return True, ""
        return False, f"User {user_id} not authorized"

    @staticmethod
    def sanitize_message(text: str) -> tuple[str, bool]:
        """Layer 2: Return (cleaned_text, is_blocked). blocked=True → reject."""
        if not isinstance(text, str):
            return "", True
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        cleaned = cleaned[:MAX_MESSAGE_LENGTH]
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(cleaned):
                return cleaned, True
        return cleaned, False

    def check_capability_access(self, capability_id: str) -> str:
        """Layer 3: Return 'allow', 'confirm', or 'blocked'."""
        if capability_id in self.blocked_capabilities:
            return "blocked"
        if capability_id in self.confirm_required:
            return "confirm"
        return "allow"


class ChannelPollingWorker:
    """Generic polling worker that routes messages through the CapOS pipeline.

    Subclasses implement _fetch_updates() and _extract_message() for
    platform-specific API calls. Everything else (security, interpretation,
    execution, recording, confirmation) is handled here.
    """

    channel_name: str = "channel"  # override in subclass (e.g. "slack", "discord")
    poll_interval: float = 3.0

    def __init__(
        self,
        adapter: ChannelAdapter,
        interpreter: Any = None,
        executor: Any = None,
        execution_history: Any = None,
    ):
        self._adapter = adapter
        self._interpreter = interpreter
        self._executor = executor
        self._history = execution_history
        self._running = False
        self._thread: threading.Thread | None = None
        self._pending: dict[str, dict[str, Any]] = {}
        self._chat_messages: dict[str, list[dict[str, Any]]] = {}

    @property
    def running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name=f"{self.channel_name}-poll",
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def get_status(self) -> dict[str, Any]:
        return {"running": self.running}

    # ── Abstract methods ──

    @abc.abstractmethod
    def _fetch_updates(self) -> list[dict[str, Any]]:
        """Fetch new messages from the platform. Return list of raw updates."""

    @abc.abstractmethod
    def _extract_message(self, update: dict[str, Any]) -> tuple[str, str, str, str] | None:
        """Extract (channel_id, user_id, text, user_display_name) from a raw update.
        Return None to skip the update."""

    def _send_typing(self, channel_id: str) -> None:
        """Optional: send typing indicator. Override if platform supports it."""

    def _reply(self, channel_id: str, text: str) -> None:
        """Send a reply message."""
        try:
            self._adapter.send_message(channel_id, (text or "...")[:4096])
        except Exception as exc:
            print(f"[{self.channel_name.upper()}-POLL] reply error: {exc}", flush=True)

    # ── Poll loop ──

    def _poll_loop(self) -> None:
        tag = self.channel_name.upper()
        print(f"[{tag}-POLL] Polling started", flush=True)
        while self._running:
            try:
                updates = self._fetch_updates()
                for u in updates:
                    try:
                        self._process_update(u)
                    except Exception as exc:
                        print(f"[{tag}-POLL] process error: {exc}", flush=True)
            except Exception as exc:
                print(f"[{tag}-POLL] loop error: {exc}", flush=True)
                try:
                    from system.core.ui_bridge.event_bus import event_bus
                    event_bus.emit("error", {"source": f"{self.channel_name}_polling", "message": str(exc)[:300]})
                except Exception:
                    pass
            try:
                time.sleep(self.poll_interval)
            except Exception:
                pass
        print(f"[{tag}-POLL] Polling stopped", flush=True)

    def _process_update(self, update: dict[str, Any]) -> None:
        extracted = self._extract_message(update)
        if extracted is None:
            return
        channel_id, user_id, text, display_name = extracted

        # Layer 1: Authorization
        ok, reason = self._adapter.is_authorized(user_id)
        if not ok:
            return

        if not text.strip():
            return

        # Pending confirmation?
        if channel_id in self._pending:
            self._handle_confirmation(channel_id, text)
            return

        # Layer 2: Sanitization
        cleaned, blocked = ChannelAdapter.sanitize_message(text)
        if blocked:
            self._reply(channel_id, "I can't process that message.")
            return

        # Emit event
        try:
            from system.core.ui_bridge.event_bus import event_bus
            event_bus.emit(f"{self.channel_name}_message", {
                "channel_id": channel_id, "user": display_name, "text": text[:200],
            })
        except Exception:
            pass

        self._send_typing(channel_id)
        self._handle_message(channel_id, cleaned, display_name)

    # ── Message handling ──

    def _handle_message(self, channel_id: str, text: str, user_name: str) -> None:
        if self._interpreter is None:
            self._reply(channel_id, "System not ready.")
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
                self._reply(channel_id, "I didn't understand that. Can you be more specific?")
                return

            steps: list[dict[str, Any]] = []
            if suggestion.get("type") == "capability":
                steps = [{"capability": suggestion.get("capability"), "inputs": suggestion.get("inputs", {})}]
            elif suggestion.get("type") == "sequence":
                steps = suggestion.get("steps", [])

            if not steps:
                self._reply(channel_id, "I couldn't create a plan for that.")
                return

            # Layer 3: Capability sandbox
            for step in steps:
                cap = step.get("capability", "")
                access = self._adapter.check_capability_access(cap)
                if access == "blocked":
                    self._reply(channel_id, f"That action ({cap}) is not allowed from {self.channel_name}.")
                    return
                if access == "confirm":
                    self._pending[channel_id] = {"steps": steps, "expires": time.time() + 60}
                    inputs_str = json.dumps(step.get("inputs", {}), ensure_ascii=False)[:200]
                    self._reply(channel_id, f"This action requires confirmation:\n{cap}\n{inputs_str}\n\nReply yes to confirm or no to cancel.")
                    return

            self._execute_steps(channel_id, steps, text, t0, user_name)

        except Exception as exc:
            self._reply(channel_id, f"Error: {str(exc)[:200]}")

    def _execute_steps(self, channel_id: str, steps: list[dict[str, Any]], original_text: str = "", t0: float = 0, user_name: str = "") -> None:
        if self._executor is None:
            self._reply(channel_id, "Executor not available.")
            return
        self._reply(channel_id, f"Executing {len(steps)} step(s)...")
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
                    err = result.get("error_message", "Unknown error") if result else "No result"
                    self._reply(channel_id, f"Error in {cap}: {err}")
                    return
            except Exception as exc:
                self._reply(channel_id, f"Error in {cap}: {str(exc)[:200]}")
                return
        if last_response:
            self._record(original_text, last_response, t0, user_name, channel_id)

    def _handle_confirmation(self, channel_id: str, text: str) -> None:
        pending = self._pending.get(channel_id)
        if not pending:
            return
        if time.time() > pending["expires"]:
            del self._pending[channel_id]
            self._reply(channel_id, "Confirmation expired. Repeat the command.")
            return
        lower = text.lower().strip()
        if lower in ("yes", "si", "y", "s"):
            del self._pending[channel_id]
            self._execute_steps(channel_id, pending["steps"])
        elif lower in ("no", "n", "cancel", "cancelar"):
            del self._pending[channel_id]
            self._reply(channel_id, "Action cancelled.")
        else:
            self._reply(channel_id, "Reply yes or no.")

    # ── Formatting ──

    @staticmethod
    def _format_output(cap: str, output: dict[str, Any]) -> str:
        if "items" in output:
            items = output["items"]
            lines = [f"{len(items)} items:"]
            for it in items[:20]:
                icon = "dir" if it.get("type") == "directory" else "file"
                lines.append(f"  {icon}  {it.get('name', '?')}")
            if len(items) > 20:
                lines.append(f"  ...and {len(items) - 20} more")
            return "\n".join(lines)
        if "content" in output:
            return str(output["content"])[:3000]
        text = json.dumps(output, indent=2, ensure_ascii=False)
        if len(text) > 3000:
            text = text[:3000] + "\n...(truncated)"
        return text

    # ── Recording ──

    def _record(self, intent: str, response: str, t0: float, user_name: str, channel_id: str = "") -> None:
        if self._history is None:
            return
        try:
            elapsed = int((time.monotonic() - t0) * 1000) if t0 else 0
            sid = f"{self.channel_name}_{channel_id}" if channel_id else f"{self.channel_name}_{int(time.time())}"
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
            tag = self.channel_name.upper()[:2]
            self._history.upsert_chat(
                session_id=sid,
                intent=f"[{tag} @{user_name}] {first_intent or intent[:100]}",
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
