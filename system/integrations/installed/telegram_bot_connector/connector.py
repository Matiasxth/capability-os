"""Telegram Bot API connector for Capability OS.

Three security layers:
  1. User whitelist (allowed_user_ids / allowed_usernames)
  2. Prompt-injection detection (regex blocklist)
  3. Capability sandboxing (blocked / confirm-required lists)

Uses only stdlib (urllib) — no external dependencies.
"""
from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


_API_BASE = "https://api.telegram.org/bot{token}/{method}"

# ── Security: capabilities sandbox ──

TELEGRAM_BLOCKED_CAPABILITIES = frozenset({
    "install_integration", "uninstall_integration",
    "approve_proposal", "reject_proposal",
    "update_settings", "system_settings",
    "send_telegram_message", "send_telegram_photo",
    "get_telegram_updates",
})

TELEGRAM_CONFIRM_REQUIRED = frozenset({
    "write_file", "filesystem_write_file",
    "delete_file", "filesystem_delete_file",
    "delete_directory", "filesystem_delete_directory",
    "move_file", "filesystem_move_file",
    "copy_file", "filesystem_copy_file",
    "execute_script", "execution_run_script",
    "execution_run_command",
})

# ── Security: prompt injection patterns ──

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

_MAX_MESSAGE_LENGTH = 2000


class TelegramConnectorError(RuntimeError):
    """Structured error for Telegram operations."""

    def __init__(self, message: str, error_code: str = "telegram_error", details: dict[str, Any] | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


class TelegramConnector:
    """Telegram Bot API connector with security layers."""

    def __init__(
        self,
        bot_token: str = "",
        default_chat_id: str = "",
        allowed_user_ids: list[int | str] | None = None,
        allowed_usernames: list[str] | None = None,
        user_display_names: dict[str, str] | None = None,
    ):
        self._bot_token = bot_token
        self._default_chat_id = self._validate_chat_id(default_chat_id)
        self._bot_id: str | None = None  # cached from getMe
        self._allowed_user_ids = [str(i) for i in (allowed_user_ids or [])]
        self._allowed_usernames = list(allowed_usernames or [])
        self._user_display_names: dict[str, str] = user_display_names or {}  # user_id → display name

    def configure(
        self,
        bot_token: str,
        default_chat_id: str = "",
        allowed_user_ids: list[int | str] | None = None,
        allowed_usernames: list[str] | None = None,
    ) -> None:
        self._bot_token = bot_token
        if default_chat_id:
            self._default_chat_id = default_chat_id
        if allowed_user_ids is not None:
            self._allowed_user_ids = [str(i) for i in allowed_user_ids]
        if allowed_usernames is not None:
            self._allowed_usernames = list(allowed_usernames)

    def set_user_display_names(self, names: dict[str, str]) -> None:
        self._user_display_names = dict(names)

    # ------------------------------------------------------------------
    # Layer 1 — Authorization
    # ------------------------------------------------------------------

    def is_authorized(self, update: dict[str, Any]) -> tuple[bool, str]:
        user = update.get("message", {}).get("from", {})
        user_id = str(user.get("id", ""))
        username = user.get("username", "")
        if not self._allowed_user_ids and not self._allowed_usernames:
            return False, "No authorized users configured"
        if user_id in self._allowed_user_ids:
            return True, ""
        if username and username in self._allowed_usernames:
            return True, ""
        return False, f"User {user_id} (@{username}) not authorized"

    # ------------------------------------------------------------------
    # Layer 2 — Prompt injection detection
    # ------------------------------------------------------------------

    @staticmethod
    def sanitize_message(text: str) -> tuple[str, bool]:
        """Return (cleaned_text, is_blocked). blocked=True means reject."""
        if not isinstance(text, str):
            return "", True
        # Strip control characters
        cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        # Truncate
        cleaned = cleaned[:_MAX_MESSAGE_LENGTH]
        # Check injection patterns
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(cleaned):
                return cleaned, True
        return cleaned, False

    # ------------------------------------------------------------------
    # Layer 3 — Capability sandbox
    # ------------------------------------------------------------------

    @staticmethod
    def check_capability_access(capability_id: str) -> str:
        """Return 'allow', 'confirm', or 'blocked'."""
        if capability_id in TELEGRAM_BLOCKED_CAPABILITIES:
            return "blocked"
        if capability_id in TELEGRAM_CONFIRM_REQUIRED:
            return "confirm"
        return "allow"

    # ------------------------------------------------------------------
    # Capability handlers
    # ------------------------------------------------------------------

    def send_telegram_message(self, inputs: dict[str, Any]) -> dict[str, Any]:
        message = inputs.get("message", "")
        if not isinstance(message, str) or not message.strip():
            raise TelegramConnectorError("Field 'message' is required.", "invalid_input")
        chat_id = inputs.get("chat_id") or self._default_chat_id
        if not chat_id:
            raise TelegramConnectorError(
                "No chat_id provided and no default configured.",
                "no_chat_id",
            )
        params: dict[str, Any] = {"chat_id": chat_id, "text": message}
        parse_mode = inputs.get("parse_mode")
        if parse_mode:
            params["parse_mode"] = parse_mode
        result = self._api_call("sendMessage", params)
        return {"status": "success", "message_id": result.get("message_id"), "chat_id": str(chat_id)}

    def send_telegram_photo(self, inputs: dict[str, Any]) -> dict[str, Any]:
        photo_path = inputs.get("photo_path", "")
        if not photo_path or not Path(photo_path).exists():
            raise TelegramConnectorError(f"Photo not found: {photo_path}", "file_not_found")
        chat_id = inputs.get("chat_id") or self._default_chat_id
        if not chat_id:
            raise TelegramConnectorError("No chat_id provided and no default configured.", "no_chat_id")
        result = self._api_multipart("sendPhoto", chat_id, photo_path, inputs.get("caption", ""))
        return {"status": "success", "message_id": result.get("message_id"), "chat_id": str(chat_id)}

    def get_telegram_updates(self, inputs: dict[str, Any]) -> dict[str, Any]:
        limit = inputs.get("limit", 10)
        if not isinstance(limit, int) or limit < 1:
            limit = 10
        raw = self._api_call("getUpdates", {"limit": limit, "allowed_updates": ["message"]})
        messages: list[dict[str, Any]] = []
        for update in raw or []:
            msg = update.get("message", {})
            if msg:
                messages.append({
                    "id": msg.get("message_id"),
                    "from": msg.get("from", {}).get("username", ""),
                    "text": msg.get("text", ""),
                    "date": msg.get("date"),
                })
        return {"status": "success", "messages": messages, "count": len(messages)}

    # ------------------------------------------------------------------
    # Validation / Status
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_chat_id(chat_id: str) -> str:
        """Return chat_id only if it looks like a valid numeric Telegram ID, or @username."""
        if not chat_id:
            return ""
        stripped = str(chat_id).strip()
        # Numeric IDs (including negative for groups)
        try:
            int(stripped)
            return stripped
        except (ValueError, TypeError):
            pass
        # @username format
        if stripped.startswith("@"):
            return stripped
        # Invalid — not a usable chat_id
        return ""

    def validate(self) -> dict[str, Any]:
        try:
            result = self._api_call("getMe")
            self._bot_id = str(result.get("id", ""))
            return {"valid": True, "bot_name": result.get("username"), "bot_id": result.get("id")}
        except TelegramConnectorError as exc:
            return {"valid": False, "error": str(exc)}

    def get_status(self) -> dict[str, Any]:
        configured = bool(self._bot_token)
        if not configured:
            return {"configured": False, "connected": False}
        v = self.validate()
        return {
            "configured": True,
            "connected": v.get("valid", False),
            "bot_name": v.get("bot_name"),
            "default_chat_id": self._default_chat_id or None,
            "allowed_user_ids": self._allowed_user_ids,
        }

    # ------------------------------------------------------------------
    # Internal HTTP
    # ------------------------------------------------------------------

    def _api_call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if not self._bot_token:
            raise TelegramConnectorError("Bot token not configured.", "not_configured")
        url = _API_BASE.format(token=self._bot_token, method=method)
        data = json.dumps(params or {}).encode("utf-8")
        req = Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "CapabilityOS/1.0"})
        try:
            with urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            detail = ""
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("description", "")
            except Exception:
                pass
            raise TelegramConnectorError(f"Telegram API error: {detail or exc}", "api_error") from exc
        except URLError as exc:
            raise TelegramConnectorError(f"Connection failed: {exc.reason}", "connection_error") from exc
        if not body.get("ok"):
            raise TelegramConnectorError(body.get("description", "Unknown Telegram error"), "api_error")
        return body.get("result")

    def _api_multipart(self, method: str, chat_id: str, file_path: str, caption: str = "") -> Any:
        if not self._bot_token:
            raise TelegramConnectorError("Bot token not configured.", "not_configured")
        url = _API_BASE.format(token=self._bot_token, method=method)
        boundary = "----CapOSBoundary9f8e7d"
        parts: list[bytes] = []
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n".encode())
        if caption:
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n".encode())
        filename = Path(file_path).name
        with open(file_path, "rb") as f:
            file_data = f.read()
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
            + file_data + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        req = Request(url, data=b"".join(parts), headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "CapabilityOS/1.0",
        })
        try:
            with urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            raise TelegramConnectorError(f"Photo upload failed: {exc}", "api_error") from exc
        if not result.get("ok"):
            raise TelegramConnectorError(result.get("description", "Upload failed"), "api_error")
        return result.get("result", {})


# ======================================================================
# Polling worker — runs in a daemon thread
# ======================================================================

class TelegramPollingWorker:
    """Polls Telegram for messages and routes them through the CapOS pipeline."""

    def __init__(
        self,
        connector: TelegramConnector,
        interpreter: Any = None,
        executor: Any = None,
        execution_history: Any = None,
    ):
        self._connector = connector
        self._interpreter = interpreter
        self._executor = executor
        self._history = execution_history
        self._running = False
        self._thread: threading.Thread | None = None
        self._last_update_id = 0
        self._pending: dict[str, dict[str, Any]] = {}  # chat_id → {plan, expires}
        self._chat_messages: dict[str, list[dict[str, Any]]] = {}  # chat_id → accumulated messages

    @property
    def running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        # Cache bot_id to detect self-messages
        if not self._connector._bot_id:
            try:
                self._connector.validate()
            except Exception:
                pass
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="telegram-poll")
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def get_status(self) -> dict[str, Any]:
        return {"running": self.running, "last_update_id": self._last_update_id}

    # ------------------------------------------------------------------
    # Poll loop
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        print("[TELEGRAM-POLL] Polling started", flush=True)
        while self._running:
            try:
                updates = self._fetch_updates()
                if updates:
                    print(f"[TELEGRAM-POLL] Got {len(updates)} update(s)", flush=True)
                for u in updates:
                    try:
                        self._process_update(u)
                    except Exception as exc:
                        print(f"[TELEGRAM-POLL] process error: {exc}", flush=True)
            except Exception as exc:
                print(f"[TELEGRAM-POLL] loop error: {exc}", flush=True)
                try:
                    from system.core.ui_bridge.event_bus import event_bus
                    event_bus.emit("error", {"source": "telegram_polling", "message": str(exc)[:300]})
                except Exception:
                    pass
            try:
                time.sleep(3)
            except Exception:
                pass
        print("[TELEGRAM-POLL] Polling stopped", flush=True)

    def _fetch_updates(self) -> list[dict[str, Any]]:
        try:
            result = self._connector._api_call("getUpdates", {
                "offset": self._last_update_id + 1,
                "limit": 10,
                "timeout": 2,
            })
        except TelegramConnectorError:
            return []
        updates = result or []
        if updates:
            self._last_update_id = updates[-1].get("update_id", self._last_update_id)
        return updates

    def _process_update(self, update: dict[str, Any]) -> None:
        msg = update.get("message")
        if not msg:
            return
        user = msg.get("from", {})
        user_id = str(user.get("id", ""))
        # Block messages from the bot itself (prevent loops)
        if self._connector._bot_id and user_id == self._connector._bot_id:
            return
        if user.get("is_bot"):
            return
        # Layer 1: Authorization
        ok, reason = self._connector.is_authorized(update)
        if not ok:
            return  # Silent — don't reveal bot exists
        chat_id = str(msg["chat"]["id"])
        text = (msg.get("text") or "").strip()
        if not text:
            return

        # Check pending confirmation
        if chat_id in self._pending:
            self._handle_confirmation(chat_id, text)
            return

        # Layer 2: Sanitization
        cleaned, blocked = TelegramConnector.sanitize_message(text)
        if blocked:
            print(f"[TELEGRAM-POLL] Blocked message from {user.get('first_name','?')}: injection detected", flush=True)
            self._reply(chat_id, "I can't process that message.")
            return

        print(f"[TELEGRAM-POLL] Processing from {user.get('first_name','?')}: {text[:60]}", flush=True)

        try:
            from system.core.ui_bridge.event_bus import event_bus
            event_bus.emit("telegram_message", {"chat_id": chat_id, "user": user.get("first_name", ""), "text": text[:200]})
        except Exception:
            pass

        # Show typing indicator
        try:
            self._connector._api_call("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        except TelegramConnectorError:
            pass

        self._handle_message(chat_id, cleaned, user)

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    def _resolve_user_name(self, user: dict[str, Any]) -> str:
        """Return the configured display name, falling back to Telegram profile name."""
        user_id = str(user.get("id", ""))
        configured = self._connector._user_display_names.get(user_id)
        if configured:
            return configured
        return user.get("first_name", "User")

    def _handle_message(self, chat_id: str, text: str, user: dict[str, Any]) -> None:
        if self._interpreter is None:
            self._reply(chat_id, "System not ready.")
            return
        t0 = time.monotonic()
        user_name = self._resolve_user_name(user)
        try:
            msg_type = self._interpreter.classify_message(text)
            if msg_type == "conversational":
                response = self._interpreter.chat_response(text, user_name)
                self._reply(chat_id, response)
                self._record(text, response, t0, user_name, chat_id)
                return

            # Action — interpret and plan
            interpretation = self._interpreter.interpret(text)
            suggestion = interpretation.get("suggestion", {})
            if suggestion.get("type") == "unknown":
                self._reply(chat_id, "I didn't understand that. Can you be more specific?")
                return

            # Build steps list
            steps = []
            if suggestion.get("type") == "capability":
                steps = [{"capability": suggestion.get("capability"), "inputs": suggestion.get("inputs", {})}]
            elif suggestion.get("type") == "sequence":
                steps = suggestion.get("steps", [])

            if not steps:
                self._reply(chat_id, "I couldn't create a plan for that.")
                return

            # Layer 3: Capability sandbox
            for step in steps:
                cap = step.get("capability", "")
                access = TelegramConnector.check_capability_access(cap)
                if access == "blocked":
                    self._reply(chat_id, f"That action ({cap}) is not allowed from Telegram.")
                    return
                if access == "confirm":
                    self._pending[chat_id] = {"steps": steps, "expires": time.time() + 60}
                    inputs_str = json.dumps(step.get("inputs", {}), ensure_ascii=False)[:200]
                    self._reply(chat_id, f"This action requires confirmation:\n*{cap}*\n{inputs_str}\n\nReply *yes* to confirm or *no* to cancel.", parse_mode="Markdown")
                    return

            # Execute
            self._execute_steps(chat_id, steps, text, t0, user_name)

        except Exception as exc:
            self._reply(chat_id, f"Error: {str(exc)[:200]}")

    def _execute_steps(self, chat_id: str, steps: list[dict[str, Any]], original_text: str = "", t0: float = 0, user_name: str = "") -> None:
        if self._executor is None:
            self._reply(chat_id, "Executor not available.")
            return
        self._reply(chat_id, f"Executing {len(steps)} step(s)...")
        last_response = ""
        for step in steps:
            cap = step.get("capability", "")
            inputs = step.get("inputs", {})
            try:
                result = self._executor(cap, inputs)
                if result and result.get("status") == "success":
                    output = result.get("final_output", {})
                    formatted = self._format_output(cap, output)
                    self._reply(chat_id, formatted, parse_mode="Markdown")
                    last_response = formatted
                else:
                    err = result.get("error_message", "Unknown error") if result else "No result"
                    self._reply(chat_id, f"Error in {cap}: {err}")
                    return
            except Exception as exc:
                self._reply(chat_id, f"Error in {cap}: {str(exc)[:200]}")
                return
        if last_response:
            self._record(original_text, last_response, t0, user_name, chat_id)

    def _handle_confirmation(self, chat_id: str, text: str) -> None:
        pending = self._pending.get(chat_id)
        if not pending:
            return
        if time.time() > pending["expires"]:
            del self._pending[chat_id]
            self._reply(chat_id, "Confirmation expired. Repeat the command.")
            return
        lower = text.lower().strip()
        if lower in ("yes", "si", "y", "s"):
            del self._pending[chat_id]
            self._execute_steps(chat_id, pending["steps"])
        elif lower in ("no", "n", "cancel", "cancelar"):
            del self._pending[chat_id]
            self._reply(chat_id, "Action cancelled.")
        else:
            self._reply(chat_id, "Reply *yes* or *no*.", parse_mode="Markdown")

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_output(cap: str, output: dict[str, Any]) -> str:
        if "items" in output:
            items = output["items"]
            lines = [f"*{len(items)} items:*"]
            for it in items[:20]:
                icon = "dir" if it.get("type") == "directory" else "file"
                lines.append(f"  {icon}  {it.get('name', '?')}")
            if len(items) > 20:
                lines.append(f"  ...and {len(items) - 20} more")
            return "\n".join(lines)
        if "content" in output:
            content = str(output["content"])[:3000]
            return f"```\n{content}\n```"
        text = json.dumps(output, indent=2, ensure_ascii=False)
        if len(text) > 3000:
            text = text[:3000] + "\n...(truncated)"
        return f"```\n{text}\n```"

    # ------------------------------------------------------------------
    # Reply helper
    # ------------------------------------------------------------------

    def _record(self, intent: str, response: str, t0: float, user_name: str, chat_id: str = "") -> None:
        """Accumulate messages and save to execution_history."""
        if self._history is None:
            return
        try:
            elapsed = int((time.monotonic() - t0) * 1000) if t0 else 0
            sid = f"telegram_{chat_id}" if chat_id else f"telegram_{int(time.time())}"
            # Accumulate messages for this chat
            if chat_id not in self._chat_messages:
                self._chat_messages[chat_id] = []
            buf = self._chat_messages[chat_id]
            buf.append({"role": "user", "content": intent, "type": "chat"})
            buf.append({"role": "assistant", "content": response[:500], "type": "chat"})
            # Keep last 20 messages
            if len(buf) > 20:
                self._chat_messages[chat_id] = buf[-20:]
                buf = self._chat_messages[chat_id]
            # First user message as session title
            first_intent = ""
            for m in buf:
                if m["role"] == "user":
                    first_intent = m["content"][:100]
                    break
            self._history.upsert_chat(
                session_id=sid,
                intent=f"[TG @{user_name}] {first_intent or intent[:100]}",
                messages=list(buf),
                duration_ms=elapsed,
            )
            try:
                from system.core.ui_bridge.event_bus import event_bus
                event_bus.emit("session_updated", {"session_id": sid})
            except Exception:
                pass
        except Exception:
            pass  # Rule 5

    def _reply(self, chat_id: str, text: str, parse_mode: str | None = None) -> None:
        try:
            params: dict[str, Any] = {"chat_id": chat_id, "text": (text or "...")[:4096]}
            if parse_mode:
                params["parse_mode"] = parse_mode
            self._connector._api_call("sendMessage", params)
            print(f"[TELEGRAM-POLL] Reply sent to {chat_id} ({len(text)} chars)", flush=True)
        except Exception as exc:
            print(f"[TELEGRAM-POLL] reply error: {exc}", flush=True)
