"""Colorized terminal output for CapOS CLI."""
from __future__ import annotations

import sys

# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"

# Disable colors if not a TTY
if not sys.stdout.isatty():
    RESET = BOLD = DIM = CYAN = GREEN = YELLOW = RED = MAGENTA = BLUE = ""


def header(text: str) -> str:
    return f"{BOLD}{CYAN}{text}{RESET}"


def success(text: str) -> str:
    return f"{GREEN}{text}{RESET}"


def error(text: str) -> str:
    return f"{RED}{text}{RESET}"


def warn(text: str) -> str:
    return f"{YELLOW}{text}{RESET}"


def dim(text: str) -> str:
    return f"{DIM}{text}{RESET}"


def accent(text: str) -> str:
    return f"{MAGENTA}{text}{RESET}"


def tool_call(tool_id: str, level: int = 1) -> str:
    level_str = f"L{level}"
    color = GREEN if level == 1 else YELLOW if level == 2 else RED
    return f"  {DIM}|{RESET} {color}{level_str}{RESET} {BOLD}{tool_id}{RESET}"


def tool_result(tool_id: str, ok: bool) -> str:
    icon = f"{GREEN}OK{RESET}" if ok else f"{RED}FAIL{RESET}"
    return f"  {DIM}|{RESET} {icon} {dim(tool_id)}"


def agent_response(text: str) -> str:
    return f"\n{CYAN}CapOS:{RESET} {text}\n"


def plugin_status(pid: str, state: str, err: str | None = None) -> str:
    if state == "running":
        icon = f"{GREEN}*{RESET}"
    elif state in ("initialized", "stopped"):
        icon = f"{YELLOW}*{RESET}"
    else:
        icon = f"{RED}*{RESET}"
    line = f"  {icon} {pid}: {state}"
    if err:
        line += f" {DIM}({err[:50]}){RESET}"
    return line
