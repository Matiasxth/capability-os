"""CLI entry point: ``python -m capabilityos``."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="capabilityos",
        description="CapabilityOS — AI Operating System CLI",
    )
    sub = parser.add_subparsers(dest="command")

    # chat
    chat_p = sub.add_parser("chat", help="Chat with the agent (interactive or one-shot)")
    chat_p.add_argument("message", nargs="?", default=None, help="One-shot message")
    chat_p.add_argument("--agent", "-a", default=None, help="Agent ID to use")
    chat_p.add_argument("--workspace", "-w", default=None, help="Workspace ID")

    # status
    sub.add_parser("status", help="Show system status and plugin health")

    # serve
    serve_p = sub.add_parser("serve", help="Start the CapOS server")
    serve_p.add_argument("--port", "-p", type=int, default=8000)
    serve_p.add_argument("--host", default="0.0.0.0")
    serve_p.add_argument("--sync", action="store_true", help="Force sync server (no uvicorn)")

    # plugins
    plug_p = sub.add_parser("plugins", help="Manage plugins")
    plug_sub = plug_p.add_subparsers(dest="plugin_cmd")
    plug_sub.add_parser("list", help="List all plugins and their status")
    inst_p = plug_sub.add_parser("install", help="Install a plugin from directory")
    inst_p.add_argument("path", help="Path to plugin directory")

    # version
    sub.add_parser("version", help="Show version")

    args = parser.parse_args()

    if args.command == "chat":
        from capabilityos.cli.chat import run_chat
        run_chat(args.message, agent_id=args.agent, workspace_id=args.workspace)
    elif args.command == "status":
        from capabilityos.cli.status import run_status
        run_status()
    elif args.command == "serve":
        from capabilityos.cli.serve import run_serve
        run_serve(host=args.host, port=args.port, sync=args.sync)
    elif args.command == "plugins":
        from capabilityos.cli.plugins import run_plugins
        run_plugins(args.plugin_cmd, args)
    elif args.command == "version":
        from capabilityos import __version__
        print(f"CapabilityOS v{__version__}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
