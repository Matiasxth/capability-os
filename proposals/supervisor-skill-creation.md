# Plan: Supervisor crea skills con aprobación del usuario

## Problema
Cuando el usuario pide al Supervisor crear una skill:
1. Claude intenta escribir archivos directamente → no tiene permisos
2. No hay forma de previsualizar el código antes de instalarlo
3. No hay confirmación del usuario
4. No se sabe dónde queda la skill ni cómo activarla

## Solución

### Flujo completo

```
1. Usuario: "crea una skill para monitorear sitios web"
2. Supervisor detecta que es una solicitud de skill
3. Supervisor invoca Claude con prompt especial:
   "Genera el código para esta skill. Retorna JSON."
4. Claude retorna JSON con: tool_id, contract, handler_code
5. Supervisor parsea el JSON
6. Frontend muestra PREVIEW:
   ┌────────────────────────────────────┐
   │ 🔧 New Skill: web_monitor         │
   │                                    │
   │ Description: Monitors website...   │
   │                                    │
   │ Code Preview:                      │
   │ ┌──────────────────────────────┐  │
   │ │ def handle_web_monitor(...): │  │
   │ │   url = params.get("url")    │  │
   │ │   ...                        │  │
   │ └──────────────────────────────┘  │
   │                                    │
   │ Tools: 1 | Dependencies: requests  │
   │                                    │
   │ [Install] [Edit] [Discard]         │
   └────────────────────────────────────┘
7. Usuario click "Install"
8. SkillCreator.create_and_load() → hot-reload
9. Mensaje: "✅ Skill web_monitor instalada y activa"
```

## Implementación

### 1. Mejorar Claude Bridge para skill generation

**`system/core/supervisor/claude_bridge.py`**:
- Mejorar `design_skill()` con prompt más completo
- El prompt incluye lista de tools existentes como referencia
- Forzar formato JSON estricto en la respuesta
- Parsear y validar la respuesta

### 2. Endpoint para generar skill via Supervisor

**`system/core/ui_bridge/handlers/supervisor_handlers.py`**:
- Nuevo: `supervisor_generate_skill(service, payload)`
  - Recibe `{description}` del chat
  - Invoca `claude_bridge.design_skill(description)`
  - Retorna el spec sin instalar (preview mode)
  - `{"status": "preview", "skill": {tool_id, name, description, contract, handler_code, dependencies}}`

- Nuevo: `supervisor_install_skill(service, payload)`
  - Recibe el spec aprobado
  - Llama a `skill_creator.create_and_load()`
  - Retorna resultado

### 3. Detección automática en el chat

**`system/core/ui_bridge/handlers/supervisor_handlers.py`** — modificar `supervisor_invoke_claude`:
- Después de recibir respuesta de Claude, detectar si contiene JSON de skill
- Si contiene: parsear y retornar como `{"type": "skill_preview", "skill": {...}}`
- Si no: retornar texto normal
- Patterns de detección: "tool_id", "handler_code", "def handle_"

### 4. Frontend: preview + install en el chat

**`system/frontend/app/src/pages/ControlCenter.jsx`** — renderSupervisor:
- Cuando un mensaje del chat tiene `type: "skill_preview"`:
  - Mostrar card con: nombre, descripción, código (syntax highlight simple)
  - Botones: "Install", "Edit" (abre en textarea), "Discard"
- Cuando "Install" → POST /supervisor/install-skill
- Cuando éxito → mostrar mensaje verde "Skill instalada"

### 5. Lista de skills auto-generadas

**Ya existe**: `/skills/auto-generated` retorna las skills creadas
- Agregar al dashboard del Supervisor una sección "Auto-Generated Skills"
- Toggle on/off por skill
- Botón delete

### 6. Permisos

- La generación de código (Claude) → sin permiso requerido (solo lee)
- La instalación (hot-load) → Level 2 (confirmación del usuario via botón "Install")
- Nunca se instala automáticamente sin que el usuario vea el código

## Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `supervisor/claude_bridge.py` | Mejorar design_skill() prompt |
| `handlers/supervisor_handlers.py` | Nuevo: generate_skill, install_skill + detección auto |
| `api_server.py` | Registrar rutas |
| `ControlCenter.jsx` | Preview card en chat + skill list |
| `api.js` | API functions |
| `docker-entrypoint.py` | API prefix |

## Verificación
1. Chat: "crea una skill para X" → aparece preview con código
2. Click "Install" → hot-loads → mensaje de éxito
3. El agente puede usar la skill inmediatamente sin restart
4. Skills auto-generadas aparecen en la lista del dashboard
5. Click "Discard" → no se instala nada
