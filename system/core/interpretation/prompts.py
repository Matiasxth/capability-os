from __future__ import annotations

from typing import Any, Iterable


BASE_RESTRICTIVE_PROMPT = """
You are an intent parser for Capability OS.

MOST IMPORTANT RULE:
For ANY request about listing, showing, or browsing files, use ONLY ONE list_directory step. NEVER add read_file after list_directory. list_directory ALREADY returns all the files. One step is enough.

Rules:
1. Return only valid JSON.
2. Never execute anything.
3. Never invent capabilities, tools, domains, or state names.
4. Use the MINIMUM number of steps. Most requests need only ONE step.
5. NEVER invent filenames. Only use read_file when the user names a specific file.
6. Each step's output is returned directly — no intermediate files needed.
7. Only suggest one of these formats:

   Single capability (USE THIS for most requests):
   {"type":"capability","capability":"list_directory","inputs":{"path":"."}}

   Sequence (ONLY when the user asks for multiple DIFFERENT actions):
   {"type":"sequence","steps":[
     {"step_id":"step_1","capability":"list_directory","inputs":{"path":"."}},
     {"step_id":"step_2","capability":"run_command","inputs":{"command":"git status"}}
   ]}

   Unknown:
   {"type":"unknown"}

8. Every step in a sequence MUST include "step_id" (e.g. "step_1", "step_2").
9. If intent is ambiguous, return {"type":"unknown"}.
10. Do not include prose, markdown, or code fences.
11. When the user says "my project", "my files", "here", or similar, use the default workspace path provided below. NEVER use placeholder paths like "/path/to/project" or "/your/project".
12. NEVER repeat the same capability with the same inputs in multiple steps.
""".strip()


INTENT_PROMPT_TEMPLATE = """
User text:
{user_text}

Available capabilities:
{capability_ids}
{workspace_context}
Interpret the user text and return JSON only.
""".strip()


def build_intent_prompt(
    user_text: str,
    capability_ids: Iterable[str],
    workspaces: list[dict[str, Any]] | None = None,
) -> str:
    cap_list = ", ".join(sorted(set(capability_ids)))
    ws_ctx = _build_workspace_context(workspaces)
    return INTENT_PROMPT_TEMPLATE.format(
        user_text=user_text.strip(),
        capability_ids=cap_list,
        workspace_context=ws_ctx,
    )


CLASSIFY_SYSTEM_PROMPT = """Classify the user's NEW message given the conversation context.

- "action": a request to DO something (list files, create project, read code, run command, send message, etc.), OR a confirmation of a previous action suggestion ("si", "sí", "ok", "dale", "hazlo", "yes", "claro", "adelante", "do it", "go ahead", "proceed")
- "conversational": greetings, questions about capabilities, chitchat, thanks, goodbyes, unclear or vague requests with no prior action context

IMPORTANT: Short confirmations ("si", "ok", "dale", "yes", "hazlo", "claro", "adelante") are ALWAYS "action" if the assistant previously suggested doing something.

Reply with ONLY one word: conversational or action"""

CHAT_SYSTEM_TEMPLATE = """You are CapOS, a helpful local AI assistant.
The user's name is {user_name}.
{workspace_info}You can help with: file operations, code analysis, running commands, browser automation, WhatsApp messaging, and more.

RULES:
- Respond in the SAME language the user is using
- Keep responses SHORT (2-3 sentences max)
- NEVER invent file paths — only use paths from the workspaces listed above
- If the user asks what you can do, list your main capabilities briefly
- If suggesting an action, describe what you would do clearly"""


def _format_history(history: list[dict[str, Any]] | None, max_msgs: int = 4) -> str:
    """Format conversation history for inclusion in prompts."""
    if not history:
        return ""
    lines = []
    for msg in history[-max_msgs:]:
        role = "User" if msg.get("role") == "user" else "Assistant"
        content = msg.get("content", "")
        if content:
            lines.append(f"{role}: {content}")
    if not lines:
        return ""
    return "Conversation so far:\n" + "\n".join(lines) + "\n\n"


def build_classify_prompt(
    text: str,
    history: list[dict[str, Any]] | None = None,
) -> str:
    history_text = _format_history(history, max_msgs=4)
    return f"{history_text}New message: \"{text.strip()}\"\n\nClassify:"


def build_chat_prompt(
    text: str,
    user_name: str = "User",
    workspaces: list[dict[str, Any]] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for a conversational response."""
    ws_info = ""
    if workspaces:
        ws_lines = []
        for ws in workspaces:
            name = ws.get("name", "unnamed")
            path = ws.get("path", "")
            default = " [DEFAULT]" if ws.get("is_default") else ""
            ws_lines.append(f"- {name}: {path}{default}")
        ws_info = "Available workspaces:\n" + "\n".join(ws_lines) + "\n"
    system = CHAT_SYSTEM_TEMPLATE.format(user_name=user_name, workspace_info=ws_info)
    history_text = _format_history(history, max_msgs=6)
    user = f"{history_text}User: {text.strip()}\nCapOS:"
    return system, user


def build_intent_prompt_with_history(
    user_text: str,
    capability_ids: Iterable[str],
    workspaces: list[dict[str, Any]] | None = None,
    history: list[dict[str, Any]] | None = None,
) -> str:
    """Like build_intent_prompt but includes conversation history for context."""
    cap_list = ", ".join(sorted(set(capability_ids)))
    ws_ctx = _build_workspace_context(workspaces)
    history_text = _format_history(history, max_msgs=4)
    return INTENT_PROMPT_TEMPLATE.format(
        user_text=f"{history_text}Current request: {user_text.strip()}",
        capability_ids=cap_list,
        workspace_context=ws_ctx,
    )


def _build_workspace_context(workspaces: list[dict[str, Any]] | None) -> str:
    if not workspaces:
        return ""
    lines = ["\nAvailable workspaces:"]
    default_path = None
    for ws in workspaces:
        name = ws.get("name", "unnamed")
        path = ws.get("path", "")
        access = ws.get("access", "read")
        is_default = ws.get("is_default", False)
        tag = " [DEFAULT]" if is_default else ""
        lines.append(f"- {name}: {path} (access: {access}){tag}")
        if is_default:
            default_path = path
    if default_path:
        lines.append(f"\nDefault workspace path: {default_path}")
        lines.append('Use this path when the user says "my project", "my files", "here", etc.')
    return "\n".join(lines)
