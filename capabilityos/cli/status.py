"""System status command for CapOS CLI."""
from __future__ import annotations

from pathlib import Path

from .formatter import header, success, error, dim, plugin_status, BOLD, RESET


def run_status() -> None:
    project_root = Path(__file__).resolve().parents[2]

    print(header("CapabilityOS Status"))
    print()

    # Initialize service to get container status
    print(dim("Loading system..."), flush=True)
    from system.core.ui_bridge.api_server import CapabilityOSUIBridgeService
    service = CapabilityOSUIBridgeService(workspace_root=project_root)

    # Container plugins
    if hasattr(service, "container"):
        status = service.container.get_status()
        running = sum(1 for s in status.values() if s["state"] == "running")
        errors = sum(1 for s in status.values() if s["state"] == "error")

        print(f"\n{BOLD}Plugins ({len(status)}){RESET}")
        for pid, info in status.items():
            print(plugin_status(pid, info["state"], info.get("error")))

        print(f"\n  {success(str(running))} running | {error(str(errors)) if errors else dim('0')} errors")
    else:
        print(dim("  Container not available"))

    # LLM
    if hasattr(service, "settings_service"):
        settings = service.settings_service.get_settings(mask_secrets=True)
        llm = settings.get("llm", {})
        print(f"\n{BOLD}LLM{RESET}")
        print(f"  Provider: {llm.get('provider', '?')}")
        print(f"  Model:    {llm.get('model', '?')}")
        print(f"  API Key:  {'configured' if llm.get('api_key') else 'not set'}")

    # Workspaces
    if hasattr(service, "workspace_registry") and service.workspace_registry:
        ws_list = service.workspace_registry.list()
        print(f"\n{BOLD}Workspaces ({len(ws_list)}){RESET}")
        for ws in ws_list:
            default = " (default)" if ws.get("is_default") else ""
            print(f"  {ws.get('name', '?')}: {ws.get('path', '?')}{dim(default)}")

    # Agents
    if hasattr(service, "agent_registry") and service.agent_registry:
        agents = service.agent_registry.list()
        print(f"\n{BOLD}Agents ({len(agents)}){RESET}")
        for a in agents:
            print(f"  {a.get('emoji', '')} {a.get('name', '?')} ({a.get('id', '?')})")

    # Memory
    if hasattr(service, "execution_history") and service.execution_history:
        print(f"\n{BOLD}Memory{RESET}")
        print(f"  History entries: {service.execution_history.count()}")
        if service.memory_manager:
            print(f"  Memories:        {service.memory_manager.count()}")
        if service.semantic_memory:
            print(f"  Semantic:        {service.semantic_memory.count()}")

    print()
