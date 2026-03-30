"""Supervisor Mega-Prompt — gives Claude full context of the system.

Builds a comprehensive prompt with system state, available actions,
and exact formats for skills, agents, and config changes.
"""
from __future__ import annotations

import json
from typing import Any

SUPERVISOR_ACTIONS = """
## Available Actions — respond with ONE JSON object

### 1. create_skill
{"action": "create_skill", "spec": {
  "tool_id": "snake_case_id",
  "name": "Display Name",
  "description": "What it does",
  "domain": "domain_name (e.g. pdf_tools, image_tools, data_tools)",
  "inputs": {"param": {"type": "string", "required": true, "description": "..."}},
  "outputs": {"result": {"type": "string"}},
  "handler_code": "def handle_TOOLID(params, contract):\\n    value = params.get('param')\\n    # implementation\\n    return {'status': 'success', 'result': value}",
  "handler_name": "handle_TOOLID",
  "dependencies": ["pip_package"]
}}

### 2. create_agent
{"action": "create_agent", "spec": {
  "name": "Agent Name", "emoji": "emoji", "description": "What it does",
  "system_prompt": "You are X, expert in Y. Always do Z.",
  "tool_ids": ["tool1", "tool2"],
  "language": "es", "max_iterations": 10
}}

### 3. edit_file
{"action": "edit_file", "path": "relative/path/to/file", "content": "full file content", "reason": "why this change"}

### 4. fix_config
{"action": "fix_config", "setting": "llm.model", "new_value": "gpt-4o", "reason": "why"}

### 5. diagnose
{"action": "diagnose", "analysis": {"problem": "...", "root_cause": "...", "impact": "...", "fix": "...", "severity": "low|medium|high"}}

### 6. install_package
{"action": "install_package", "package": "package_name", "reason": "why needed"}

### 7. restart_component
{"action": "restart_component", "component": "llm|browser|whatsapp|scheduler", "reason": "why"}

### 8. text (normal response)
{"action": "text", "message": "your response here"}

## Rules
- ALWAYS return valid JSON with "action" field
- For create_skill: handler_code MUST be a valid Python function with signature def handle_TOOLID(params, contract)
- For create_skill: MUST return dict with "status" key
- For create_agent: only use tool_ids from the available list below
- NEVER use eval(), exec(), os.system() or __import__ in handler_code
- Respond in the user's language
"""

AVAILABLE_TOOL_IDS = [
    "filesystem_read_file", "filesystem_write_file", "filesystem_list_directory",
    "filesystem_create_directory", "filesystem_delete_file", "filesystem_copy_file",
    "filesystem_move_file", "filesystem_edit_file",
    "execution_run_command", "execution_run_script",
    "network_http_get", "network_extract_text", "network_extract_links",
    "browser_navigate", "browser_read_text", "browser_screenshot",
    "browser_click_element", "browser_type_text",
    "system_get_os_info", "system_get_workspace_info", "system_get_env_var",
    "system_monitor_overview", "system_monitor_processes",
    "package_install", "package_list",
    "git_status", "git_log", "git_commit",
    "backup_create", "backup_list",
]


def build_mega_prompt(service: Any) -> str:
    """Build the complete supervisor prompt with system state."""
    state = _gather_state(service)

    return f"""You are the Supervisor of Capability OS — an AI-powered personal operating system.
You have full control over the system. You can create skills, agents, edit files, install packages, and more.

{SUPERVISOR_ACTIONS}

## Available tool_ids for agents
{json.dumps(AVAILABLE_TOOL_IDS, indent=2)}

## Current System State
{json.dumps(state, indent=2, ensure_ascii=False, default=str)}
"""


def _gather_state(service: Any) -> dict[str, Any]:
    """Gather current system state for context."""
    state: dict[str, Any] = {}

    # Health
    if hasattr(service, "supervisor"):
        sv = service.supervisor
        state["health"] = sv.health_monitor.status
        state["security"] = sv._security_auditor.status if hasattr(sv, "_security_auditor") else "unknown"
        state["claude_available"] = sv.claude_bridge.available
        state["recent_errors"] = [
            {"code": e.get("error_code"), "msg": e.get("message", "")[:80]}
            for e in sv.error_interceptor.recent_log[-5:]
        ]

    # LLM
    try:
        settings = service.settings_service.get_settings(mask_secrets=True)
        llm = settings.get("llm", {})
        state["llm"] = {"provider": llm.get("provider"), "model": llm.get("model")}
    except Exception:
        pass

    # Agents
    if hasattr(service, "agent_registry"):
        agents = service.agent_registry.list()
        state["agents"] = [{"id": a["id"], "name": a["name"], "tools": len(a.get("tool_ids", []))} for a in agents]

    # Skills auto-generated
    if hasattr(service, "skill_creator"):
        state["auto_skills"] = service.skill_creator.created_skills

    # Scheduler
    if hasattr(service, "task_queue"):
        state["scheduled_tasks"] = len(service.task_queue.list())

    # Gaps
    if hasattr(service, "supervisor") and hasattr(service.supervisor, "_gap_detector"):
        state["detected_gaps"] = service.supervisor._gap_detector.detected_gaps[-3:]

    return state
