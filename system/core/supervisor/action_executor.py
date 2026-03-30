"""Action Executor — parses and executes Claude's action responses.

Classifies each action into: auto (safe), preview (needs approval), confirm (dangerous).
Validates code before staging. Executes approved actions.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any


# Actions that execute immediately (safe)
AUTO_ACTIONS = {"text", "diagnose"}

# Actions that show a preview first (user approves)
PREVIEW_ACTIONS = {"create_skill", "create_agent", "edit_file", "fix_config"}

# Actions that need explicit confirmation (dangerous)
CONFIRM_ACTIONS = {"install_package", "restart_component", "run_command"}

# Dangerous patterns in handler code
DANGEROUS_PATTERNS = [
    re.compile(r'\beval\s*\('),
    re.compile(r'\bexec\s*\('),
    re.compile(r'\b__import__\s*\('),
    re.compile(r'\bos\.system\s*\('),
    re.compile(r'\bsubprocess\.call\s*\('),
    re.compile(r'\bopen\s*\(.*/etc/'),
    re.compile(r'\brm\s+-rf'),
]


def parse_action(response: str) -> dict[str, Any] | None:
    """Extract action JSON from Claude's response."""
    if not response:
        return None

    # Try to find JSON with "action" field
    if '"action"' not in response:
        return {"action": "text", "message": response}

    # Find JSON object
    start = response.find("{")
    if start < 0:
        return {"action": "text", "message": response}

    try:
        decoder = json.JSONDecoder()
        data, _ = decoder.raw_decode(response, start)
        if isinstance(data, dict) and "action" in data:
            return data
    except (json.JSONDecodeError, ValueError):
        pass

    # Fallback: try regex
    match = re.search(r'\{[\s\S]*"action"[\s\S]*\}', response)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return {"action": "text", "message": response}


def classify_action(action: dict[str, Any]) -> str:
    """Classify action into: auto, preview, confirm."""
    action_type = action.get("action", "text")
    if action_type in AUTO_ACTIONS:
        return "auto"
    if action_type in PREVIEW_ACTIONS:
        return "preview"
    if action_type in CONFIRM_ACTIONS:
        return "confirm"
    return "auto"


def validate_skill_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate a skill spec before staging. Returns {valid, errors}."""
    errors = []

    if not spec.get("tool_id"):
        errors.append("Missing tool_id")
    if not spec.get("handler_code"):
        errors.append("Missing handler_code")

    # Validate Python syntax
    code = spec.get("handler_code", "")
    if code:
        try:
            compile(code, "<skill>", "exec")
        except SyntaxError as exc:
            errors.append(f"Python syntax error: {exc}")

        # Check for dangerous patterns
        for pattern in DANGEROUS_PATTERNS:
            if pattern.search(code):
                errors.append(f"Dangerous pattern detected: {pattern.pattern}")

        # Check handler function exists
        handler_name = spec.get("handler_name", f"handle_{spec.get('tool_id', '')}")
        if f"def {handler_name}" not in code:
            errors.append(f"Handler function '{handler_name}' not found in code")

    # Validate inputs format
    inputs = spec.get("inputs", {})
    if inputs and not isinstance(inputs, dict):
        errors.append("inputs must be a dict")

    return {"valid": len(errors) == 0, "errors": errors}


def execute_auto(action: dict[str, Any]) -> dict[str, Any]:
    """Execute a safe action immediately."""
    action_type = action.get("action", "text")

    if action_type == "text":
        return {"type": "text", "content": action.get("message", "")}

    if action_type == "diagnose":
        return {"type": "diagnosis", "analysis": action.get("analysis", {})}

    return {"type": "text", "content": json.dumps(action)}


def prepare_preview(action: dict[str, Any]) -> dict[str, Any]:
    """Prepare preview data for user approval."""
    action_type = action.get("action", "")
    preview_id = f"prev_{uuid.uuid4().hex[:8]}"

    if action_type == "create_skill":
        spec = action.get("spec", {})
        validation = validate_skill_spec(spec)
        return {
            "type": "skill_preview",
            "preview_id": preview_id,
            "spec": spec,
            "validation": validation,
        }

    if action_type == "create_agent":
        return {
            "type": "agent_preview",
            "preview_id": preview_id,
            "spec": action.get("spec", {}),
        }

    if action_type == "edit_file":
        return {
            "type": "file_preview",
            "preview_id": preview_id,
            "path": action.get("path", ""),
            "content": action.get("content", ""),
            "reason": action.get("reason", ""),
        }

    if action_type == "fix_config":
        return {
            "type": "config_preview",
            "preview_id": preview_id,
            "setting": action.get("setting", ""),
            "new_value": action.get("new_value"),
            "reason": action.get("reason", ""),
        }

    if action_type == "install_package":
        return {
            "type": "command_preview",
            "preview_id": preview_id,
            "command": f"pip install {action.get('package', '')}",
            "reason": action.get("reason", ""),
        }

    if action_type == "restart_component":
        return {
            "type": "restart_preview",
            "preview_id": preview_id,
            "component": action.get("component", ""),
            "reason": action.get("reason", ""),
        }

    return {"type": "text", "content": json.dumps(action)}


def execute_approved(action_type: str, spec: dict[str, Any], service: Any) -> dict[str, Any]:
    """Execute an approved action."""
    try:
        if action_type == "create_skill" and hasattr(service, "skill_creator"):
            result = service.skill_creator.create_and_load(
                tool_id=spec.get("tool_id", ""),
                name=spec.get("name", ""),
                description=spec.get("description", ""),
                inputs=spec.get("inputs", {}),
                outputs=spec.get("outputs", {}),
                handler_code=spec.get("handler_code", ""),
                handler_name=spec.get("handler_name", ""),
                dependencies=spec.get("dependencies"),
            )
            return result

        if action_type == "create_agent" and hasattr(service, "agent_registry"):
            agent = service.agent_registry.add(
                name=spec.get("name", ""),
                emoji=spec.get("emoji", "\U0001f916"),
                description=spec.get("description", ""),
                system_prompt=spec.get("system_prompt", ""),
                tool_ids=spec.get("tool_ids"),
                language=spec.get("language", "auto"),
                max_iterations=spec.get("max_iterations", 10),
            )
            return {"status": "success", "agent": agent}

        if action_type == "fix_config":
            settings = service.settings_service.load_settings()
            # Navigate nested setting path
            parts = spec.get("setting", "").split(".")
            obj = settings
            for p in parts[:-1]:
                obj = obj.setdefault(p, {})
            obj[parts[-1]] = spec.get("new_value")
            service.settings_service.save_settings(settings)
            return {"status": "success", "setting": spec.get("setting"), "new_value": spec.get("new_value")}

        if action_type == "install_package":
            from system.tools.implementations.system_tools_extended import package_install
            return package_install({"package": spec.get("package", "")}, {})

        return {"status": "error", "error": f"Unknown action type: {action_type}"}

    except Exception as exc:
        return {"status": "error", "error": str(exc)}
