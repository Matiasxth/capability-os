"""Interactive chat and one-shot mode for CapOS CLI."""
from __future__ import annotations

import sys
from pathlib import Path

from .formatter import header, agent_response, tool_call, tool_result, dim, error, accent, BOLD, RESET


def _init_service():
    """Initialize the CapOS service (heavy — only done once)."""
    project_root = Path(__file__).resolve().parents[2]
    workspace = Path.cwd()

    print(dim("Initializing CapOS..."), flush=True)
    from system.core.ui_bridge.api_server import CapabilityOSUIBridgeService
    service = CapabilityOSUIBridgeService(workspace_root=project_root)
    print(dim("Ready.\n"), flush=True)
    return service


def run_chat(message: str | None = None, agent_id: str | None = None, workspace_id: str | None = None) -> None:
    service = _init_service()

    if not hasattr(service, "agent_loop") or service.agent_loop is None:
        print(error("Agent not available. Check LLM configuration."))
        return

    agent_config = None
    if agent_id and hasattr(service, "agent_registry") and service.agent_registry:
        agent_config = service.agent_registry.get(agent_id)
    agent_name = (agent_config or {}).get("name", "CapOS")

    if message:
        # One-shot mode
        _run_agent_message(service, message, agent_config, workspace_id, agent_name)
        return

    # Interactive mode
    print(header(f"CapOS Chat [{agent_name}]"))
    print(dim("Type 'exit' to quit, '/agents' to list agents, '/clear' to reset\n"))

    session_id = None
    history: list[dict] = []

    while True:
        try:
            prompt = f"{BOLD}{accent('>')} {RESET}"
            user_input = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n" + dim("Bye!"))
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "/exit", "/quit"):
            print(dim("Bye!"))
            break
        if user_input == "/agents":
            if hasattr(service, "agent_registry") and service.agent_registry:
                agents = service.agent_registry.list()
                for a in agents:
                    print(f"  {a.get('emoji', '')} {a['name']} ({a['id']})")
            else:
                print(dim("No agent registry"))
            continue
        if user_input == "/clear":
            session_id = None
            history = []
            print(dim("Session cleared."))
            continue
        if user_input.startswith("/agent "):
            new_id = user_input[7:].strip()
            if hasattr(service, "agent_registry") and service.agent_registry:
                cfg = service.agent_registry.get(new_id)
                if cfg:
                    agent_config = cfg
                    agent_name = cfg.get("name", new_id)
                    print(dim(f"Switched to {agent_name}"))
                else:
                    print(error(f"Agent '{new_id}' not found"))
            continue

        session_id, final = _run_agent_message(
            service, user_input, agent_config, workspace_id, agent_name, session_id,
        )


def _run_agent_message(
    service, message: str, agent_config: dict | None,
    workspace_id: str | None, agent_name: str,
    session_id: str | None = None,
) -> tuple[str | None, str]:
    """Run a single agent message, printing events in real-time."""
    ws_root = str(service.workspace_root)
    if workspace_id and hasattr(service, "workspace_registry") and service.workspace_registry:
        ws = service.workspace_registry.get(workspace_id)
        if ws and ws.get("path"):
            ws_root = ws["path"]

    gen = service.agent_loop.run(
        message,
        session_id=session_id,
        agent_config=agent_config,
        workspace_id=workspace_id,
        workspace_path=ws_root,
    )

    final_text = ""
    sid = session_id

    try:
        for event in gen:
            etype = event.get("event", "")
            if event.get("session_id"):
                sid = event["session_id"]

            if etype == "tool_call":
                print(tool_call(event["tool_id"], event.get("security_level", 1)))

            elif etype == "tool_result":
                print(tool_result(event["tool_id"], event.get("success", True)))

            elif etype == "agent_response":
                final_text = event.get("text", "")
                print(agent_response(final_text))

            elif etype == "agent_error":
                print(error(f"  Error: {event.get('error', '')}"))

            elif etype == "awaiting_confirmation":
                print(f"\n{accent('Requires confirmation:')} {event.get('description', '')}")
                print(f"  Tool: {event.get('tool_id', '')} (Level {event.get('security_level', '?')})")
                try:
                    answer = input(f"  {BOLD}Approve? [y/N]:{RESET} ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    answer = "n"
                approved = answer in ("y", "yes", "si", "s")
                # Resume
                resume_gen = service.agent_loop.resume_after_confirmation(
                    sid, event["confirmation_id"], approved, agent_config=agent_config,
                )
                for rev in resume_gen:
                    rtype = rev.get("event", "")
                    if rtype == "tool_call":
                        print(tool_call(rev["tool_id"], rev.get("security_level", 1)))
                    elif rtype == "tool_result":
                        print(tool_result(rev["tool_id"], rev.get("success", True)))
                    elif rtype == "agent_response":
                        final_text = rev.get("text", "")
                        print(agent_response(final_text))

    except StopIteration:
        pass

    return sid, final_text
