# Plan: Supervisor con Poderes Completos

## Problema Actual
El Supervisor solo conversa. No puede:
- Crear skills (Claude no sabe el formato exacto de CapOS)
- Crear agentes
- Diagnosticar errores del LLM y corregirlos
- Modificar configuración
- Reiniciar componentes

Claude intenta escribir archivos directamente pero no tiene permisos ni conoce la estructura.

## Solución: Supervisor con Contexto Completo + Acciones

### Principio: Claude NO escribe archivos. Claude GENERA specs que el sistema ejecuta.

```
Usuario: "crea una skill para monitorear webs"
     │
     ▼
Supervisor recibe el mensaje
     │
     ▼
Construye MEGA-PROMPT con:
  - Formato exacto de skills de CapOS (contract JSON + handler Python)
  - Formato exacto de agentes (registry fields)
  - Estado actual del sistema (health, errors, config)
  - Lista de tools existentes como referencia
  - Instrucciones de qué acciones puede pedir
     │
     ▼
Claude responde con ACCION JSON:
  {"action": "create_skill", "spec": {...}}
  {"action": "create_agent", "spec": {...}}
  {"action": "fix_config", "changes": {...}}
  {"action": "diagnose", "analysis": "..."}
  {"action": "restart_component", "component": "llm"}
  {"action": "text", "message": "respuesta normal"}
     │
     ▼
Supervisor parsea la acción
     │
     ├── Si es "text" → muestra en el chat
     ├── Si es "create_skill" → muestra PREVIEW → usuario aprueba → hot-load
     ├── Si es "create_agent" → muestra PREVIEW → usuario aprueba → registra
     ├── Si es "fix_config" → muestra cambios → usuario aprueba → aplica
     ├── Si es "diagnose" → muestra análisis + sugerencias
     └── Si es "restart_component" → pide confirmación → reinicia
```

## El MEGA-PROMPT del Supervisor

```python
SUPERVISOR_SYSTEM_PROMPT = """
You are the Supervisor of Capability OS. You can perform these actions by returning JSON.

## Available Actions

### 1. create_skill — Create a new tool/skill
Return:
{"action": "create_skill", "spec": {
  "tool_id": "snake_case_id",
  "name": "Display Name",
  "description": "What it does",
  "inputs": {"param_name": {"type": "string", "required": true, "description": "..."}},
  "outputs": {"result": {"type": "string"}},
  "handler_code": "def handle_TOOL_ID(params, contract):\\n    # implementation\\n    return {\\"status\\": \\"success\\", \\"result\\": \\"...\\"}",
  "handler_name": "handle_TOOL_ID",
  "dependencies": ["pip_package"]
}}

IMPORTANT handler_code rules:
- Function signature MUST be: def handle_TOOL_ID(params, contract)
- MUST return a dict with "status" key
- Use params.get("field") to read inputs
- Keep it simple, no external state

### 2. create_agent — Create a custom AI agent
Return:
{"action": "create_agent", "spec": {
  "name": "Agent Name",
  "emoji": "🤖",
  "description": "What this agent does",
  "system_prompt": "You are X, expert in Y...",
  "tool_ids": ["tool1", "tool2"],
  "language": "es",
  "max_iterations": 10
}}

Available tool_ids: filesystem_read_file, filesystem_write_file, filesystem_list_directory,
filesystem_create_directory, filesystem_delete_file, filesystem_copy_file, filesystem_move_file,
filesystem_edit_file, execution_run_command, execution_run_script, network_http_get,
network_extract_text, network_extract_links, browser_navigate, browser_read_text,
browser_screenshot, browser_click_element, browser_type_text, system_get_os_info,
system_get_workspace_info, system_get_env_var

### 3. fix_config — Modify system settings
Return:
{"action": "fix_config", "changes": {
  "path": "llm.model",
  "old_value": "current_value",
  "new_value": "new_value",
  "reason": "why this change"
}}

### 4. diagnose — Analyze a problem
Return:
{"action": "diagnose", "analysis": {
  "problem": "what went wrong",
  "root_cause": "why it happened",
  "impact": "what is affected",
  "fix": "recommended action",
  "severity": "low|medium|high"
}}

### 5. restart_component — Restart a system component
Return:
{"action": "restart_component", "component": "llm|browser|whatsapp|scheduler"}

### 6. text — Normal text response
Return:
{"action": "text", "message": "your response here"}

## Current System State
{SYSTEM_STATE}

## Rules
- ALWAYS return valid JSON with an "action" field
- For skills: handler_code must be a working Python function
- For agents: only use tool_ids from the available list
- NEVER guess — if unsure, use "diagnose" or "text" action
- Respond in the user's language
"""
```

## Implementación

### 1. Supervisor Prompt Builder (`system/core/supervisor/supervisor_prompt.py`)

```python
class SupervisorPromptBuilder:
    """Builds the mega-prompt with system context."""

    def build(self, service) -> str:
        state = {
            "health": service.supervisor.health_monitor.status,
            "llm": {
                "provider": settings.get("llm", {}).get("provider"),
                "model": settings.get("llm", {}).get("model"),
            },
            "agents": len(service.agent_registry.list()),
            "tools": len(service.tool_registry.list_all()),
            "skills_auto": len(service.skill_creator.created_skills),
            "whatsapp": service.whatsapp_manager.get_status() if hasattr(service, "whatsapp_manager") else {},
            "scheduler_tasks": len(service.task_queue.list()),
            "recent_errors": service.supervisor.error_interceptor.recent_log[-5:],
        }
        return SUPERVISOR_SYSTEM_PROMPT.replace("{SYSTEM_STATE}", json.dumps(state, indent=2))
```

### 2. Action Executor (`system/core/supervisor/action_executor.py`)

```python
class SupervisorActionExecutor:
    """Executes parsed actions from Claude's responses."""

    def execute(self, action: dict, service) -> dict:
        action_type = action.get("action")

        if action_type == "text":
            return {"type": "text", "content": action.get("message", "")}

        if action_type == "create_skill":
            # Don't install — return preview for user approval
            return {"type": "skill_preview", "spec": action["spec"]}

        if action_type == "create_agent":
            return {"type": "agent_preview", "spec": action["spec"]}

        if action_type == "fix_config":
            return {"type": "config_preview", "changes": action["changes"]}

        if action_type == "diagnose":
            return {"type": "diagnosis", "analysis": action["analysis"]}

        if action_type == "restart_component":
            return {"type": "restart_preview", "component": action["component"]}

        return {"type": "text", "content": str(action)}
```

### 3. Modificar supervisor_invoke_claude handler

```python
def supervisor_invoke_claude(service, payload):
    prompt = payload.get("prompt", "")
    # Build mega-prompt with context
    system_prompt = prompt_builder.build(service)
    full_prompt = f"{system_prompt}\n\nUser: {prompt}"

    # Get Claude's response
    response = service.supervisor.invoke_claude(full_prompt)

    # Try to parse as action JSON
    action = parse_action(response)
    if action:
        result = executor.execute(action, service)
        return result
    else:
        return {"type": "text", "content": response}
```

### 4. Install/Approve endpoints

```
POST /supervisor/approve-skill   → {spec} → skill_creator.create_and_load()
POST /supervisor/approve-agent   → {spec} → agent_registry.add()
POST /supervisor/approve-config  → {changes} → settings_service.save()
POST /supervisor/approve-restart → {component} → restart component
```

### 5. Frontend: renderizar acciones en el chat

Cuando un mensaje del Supervisor tiene tipo especial:

**skill_preview**: Card con nombre, descripción, código con scroll, botones [Install] [Discard]
**agent_preview**: Card con emoji, nombre, prompt, tools, botones [Create] [Discard]
**config_preview**: Card con cambio propuesto, botones [Apply] [Discard]
**diagnosis**: Card con análisis formateado, severity badge
**restart_preview**: Card con warning, botón [Restart] [Cancel]

### 6. LLM Error Supervision

El Error Interceptor ya captura errores del LLM. Agregar:

```python
# En error_interceptor.py
if error_code == "auth_error":
    # API key inválida
    self._notify_user("La API key del LLM es inválida. Ve a Settings → LLM para actualizarla.")

if "rate_limit" in error_code or "429" in str(message):
    # Rate limited
    self._notify_user("El LLM alcanzó el límite de requests. Esperando antes de reintentar.")
    # Auto-pause agent for 60s
    self._pause_agent(60)

if "timeout" in error_code:
    # LLM timeout
    self._notify_user("El LLM no respondió a tiempo. Puede ser un problema de red.")
    # Try to diagnose
    if self._claude.available:
        diagnosis = self._claude.diagnose(f"LLM timeout: {message}")
        self._notify_user(f"Diagnóstico: {diagnosis}")

if "model_not_found" in str(message):
    # Model doesn't exist
    self._notify_user("El modelo LLM configurado no existe. Revisa Settings → LLM.")
```

## Archivos a crear/modificar

| Archivo | Cambio |
|---------|--------|
| Nuevo: `supervisor/supervisor_prompt.py` | Mega-prompt builder con contexto |
| Nuevo: `supervisor/action_executor.py` | Parsea y ejecuta acciones de Claude |
| `supervisor/claude_bridge.py` | Aumentar timeout, mejorar prompts |
| `supervisor/error_interceptor.py` | LLM error supervision + notificaciones |
| `handlers/supervisor_handlers.py` | invoke_claude usa mega-prompt, approve endpoints |
| `api_server.py` | Registrar rutas approve-* |
| `ControlCenter.jsx` | Renderizar previews de skill/agent/config en chat |
| `api.js` | API functions approve-* |

## Verificación
1. "crea una skill para X" → preview con código → Install → funciona
2. "crea un agente experto en Y" → preview → Create → aparece en agents
3. "el LLM no responde" → supervisor diagnostica y sugiere fix
4. "cambia el modelo a gpt-4o" → preview de cambio → Apply → settings actualizado
5. Error de API key → supervisor notifica automáticamente al usuario
6. Rate limit → supervisor pausa y notifica
