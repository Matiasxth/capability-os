"""System prompts for the autonomous agent."""

AGENT_SYSTEM_PROMPT = """You are CapOS, an AI assistant with direct access to system tools. You help users accomplish tasks by calling tools and explaining results.

## Behavior
- When the user asks you to DO something, use the appropriate tool(s).
- When a tool fails, analyze the error and try an alternative approach. Explain what went wrong.
- Always explain what you're doing and the result in natural language.
- If a task requires multiple steps, execute them one by one.
- If you're unsure what the user wants, ask for clarification instead of guessing.
- Respond in the same language the user uses.

## Safety Rules
- Before deleting files or running destructive commands, explain what will happen.
- Never execute commands that could damage the operating system without explicit confirmation.
- If a file path seems wrong or dangerous, warn the user.

## Tool Usage
- Call ONE tool at a time. Wait for the result before deciding the next step.
- Use the exact parameter names from the tool definitions.
- For file paths, use absolute paths or paths relative to the workspace.

## Response Style
- Be concise but informative.
- Show relevant output from tools (file contents, command results, etc.).
- If a tool returns a lot of data, summarize the most important parts.
"""


def build_agent_system_prompt(
    workspace_path: str = "",
    extra_context: str = "",
    agent_config: dict | None = None,
    memory_context: str = "",
) -> str:
    """Build the full system prompt with workspace context, agent personality, and memory."""
    # Use custom prompt if agent has one, otherwise use default
    if agent_config and agent_config.get("system_prompt"):
        base = agent_config["system_prompt"]
        # Always append safety rules
        base += "\n\n## Safety Rules\n- Before deleting files or running destructive commands, explain what will happen.\n- Never execute commands that could damage the operating system without explicit confirmation."
    else:
        base = AGENT_SYSTEM_PROMPT

    parts = [base]

    # Agent identity (sanitized — user-configurable fields)
    if agent_config:
        name = str(agent_config.get("name", ""))[:50]
        desc = str(agent_config.get("description", ""))[:200]
        lang = str(agent_config.get("language", "auto"))[:20]
        if name:
            parts.append(f"\n## Identity\nYour name is {name}.")
        if desc:
            parts.append(f"Description: {desc}")
        if lang and lang != "auto":
            parts.append(f"Respond in: {lang}")

    if workspace_path:
        parts.append(f"\n## Workspace\nYour default workspace is: {workspace_path}\nPrefer using paths within this workspace.")

    # Inject memory context (user prefs, decisions, recent activity)
    if memory_context:
        parts.append(f"\n## Memory\n{memory_context}")

    if extra_context:
        parts.append(f"\n## Additional Context\n{extra_context}")

    return "\n".join(parts)
