"""Plugin management commands for CapOS CLI."""
from __future__ import annotations

from pathlib import Path

from .formatter import header, dim, plugin_status, success, error, BOLD, RESET


def run_plugins(cmd: str | None, args) -> None:
    if cmd == "list":
        _list_plugins()
    elif cmd == "install":
        _install_plugin(args.path)
    else:
        print(f"Usage: capabilityos plugins [list|install <path>]")


def _list_plugins() -> None:
    project_root = Path(__file__).resolve().parents[2]

    print(header("CapabilityOS Plugins"))
    print(dim("Loading..."), flush=True)

    from system.core.ui_bridge.api_server import CapabilityOSUIBridgeService
    service = CapabilityOSUIBridgeService(workspace_root=project_root)

    if not hasattr(service, "container"):
        print(error("Container not available"))
        return

    status = service.container.get_status()
    print(f"\n{BOLD}{'Plugin ID':<35} {'Name':<20} {'Version':<10} {'State':<12}{RESET}")
    print("-" * 80)

    for pid, info in sorted(status.items()):
        state = info["state"]
        color_state = success(state) if state == "running" else error(state) if state == "error" else dim(state)
        print(f"  {pid:<33} {info.get('name', '?'):<20} {info.get('version', '?'):<10} {color_state}")

    running = sum(1 for s in status.values() if s["state"] == "running")
    print(f"\n  Total: {len(status)} | Running: {success(str(running))}")


def _install_plugin(path: str) -> None:
    plugin_dir = Path(path).resolve()
    if not plugin_dir.exists():
        print(error(f"Directory not found: {plugin_dir}"))
        return

    manifest_path = plugin_dir / "capos-plugin.json"
    plugin_py = plugin_dir / "plugin.py"

    if not manifest_path.exists() and not plugin_py.exists():
        print(error(f"No capos-plugin.json or plugin.py found in {plugin_dir}"))
        return

    # Copy plugin to system/plugins/
    target_dir = Path(__file__).resolve().parents[2] / "system" / "plugins" / plugin_dir.name
    if target_dir.exists():
        print(error(f"Plugin directory already exists: {target_dir}"))
        return

    import shutil
    shutil.copytree(plugin_dir, target_dir)
    print(success(f"Plugin installed to {target_dir}"))
    print(dim("Restart the server to activate the new plugin."))
