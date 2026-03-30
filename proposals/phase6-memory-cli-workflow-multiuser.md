# Plan: Memoria Markdown + CLI Mode + Visual Workflow Builder + Multi-Usuario

---

## MÓDULO 1: MEMORIA MARKDOWN + AUTO-COMPACTION

### Problema
La memoria actual es JSON (`history.json`) — no legible por humanos, no editable, sin compaction automática. El agente pierde contexto entre sesiones largas.

### Solución

#### 1.1 Estructura de archivos
```
workspace/memory/
├── MEMORY.md                    # Decisiones permanentes, preferencias, facts
├── daily/
│   ├── 2026-03-30.md            # Notas del día
│   ├── 2026-03-29.md
│   └── ...
├── sessions/
│   ├── session_abc123.md        # Resumen compacto de cada sesión
│   └── ...
├── history.json                 # Historial detallado (existente, mantener)
└── index.json                   # Índice de memorias con metadata
```

#### 1.2 MEMORY.md (persistente)
```markdown
# CapOS Memory

## User
- Name: Matias
- Language: Spanish
- Preferences: cyberpunk theme, agent mode default

## Decisions
- 2026-03-30: WhatsApp backend set to Browser (Baileys blocked 405)
- 2026-03-30: LLM provider is Groq with llama-3.1-8b-instant

## Projects
- capability-os: AI operating system, main project
- mi-web: Personal website (in construction)

## Learned Patterns
- User prefers concise responses
- User wants confirmation before destructive actions
- System uses progressive security (3 levels)
```

#### 1.3 Daily Notes
```markdown
# 2026-03-30

## Sessions
- 14:23 Listed workspace files (7 dirs)
- 15:01 Created agent DevBot
- 16:30 Installed pdf_tools skill (auto)

## Errors
- 15:45 LLM timeout (Groq rate limit)

## Skills Created
- pdf_to_text, pdf_merge (domain: pdf_tools)
```

#### 1.4 Auto-Compaction
Antes de que el contexto del LLM se llene:
1. Detectar que el historial de mensajes excede 80% del token limit
2. Generar resumen compacto de la conversación
3. Guardar resumen en `sessions/{session_id}.md`
4. Extraer facts permanentes → agregar a `MEMORY.md`
5. Reemplazar mensajes con resumen compacto
6. Continuar la conversación con contexto reducido

```python
class MemoryCompactor:
    def should_compact(self, messages, max_tokens=4000) -> bool
    def compact(self, messages, llm_client) -> {summary, facts, compacted_messages}
    def save_to_daily(self, date, entries)
    def save_to_memory(self, facts)
    def load_context(self, session_id) -> str  # Para inyectar en prompt
```

#### 1.5 Memory en el Agent Prompt
```python
def build_agent_system_prompt(workspace_path, agent_config, memory_context):
    # Inyectar resumen de MEMORY.md + daily notes recientes
    # Max 500 tokens de contexto de memoria
```

### Archivos
| Archivo | Cambio |
|---------|--------|
| Nuevo: `system/core/memory/markdown_memory.py` | Read/write MEMORY.md, daily notes |
| Nuevo: `system/core/memory/compactor.py` | Auto-compaction + summary generation |
| `system/core/agent/agent_loop.py` | Cargar memory context antes de cada run |
| `system/core/agent/prompts.py` | Inyectar memory_context en prompt |
| `system/core/settings/settings_service.py` | Settings de compaction |

---

## MÓDULO 2: CLI MODE

### Problema
El sistema solo es accesible via web UI. Los desarrolladores quieren interactuar desde la terminal.

### Solución

#### 2.1 Comando principal
```bash
# Chat interactivo
python -m capabilityos chat
> hola
CapOS: ¡Hola! ¿En qué puedo ayudarte?
> lista los archivos
CapOS: [calls filesystem_list_directory]
  artifacts/  memory/  pagina/  skills/  system/
> exit

# Mensaje único (one-shot)
python -m capabilityos chat "que archivos hay?"

# Ejecutar capability directamente
python -m capabilityos run read_file --path ./README.md

# Estado del sistema
python -m capabilityos status

# Iniciar/parar servidor
python -m capabilityos serve
python -m capabilityos serve --port 9000
```

#### 2.2 Arquitectura
```
capabilityos/
├── __main__.py          # Entry point: python -m capabilityos
├── cli/
│   ├── __init__.py
│   ├── chat.py          # Interactive chat mode
│   ├── run.py           # Execute single capability
│   ├── status.py        # Show system status
│   └── serve.py         # Start server
```

#### 2.3 Chat interactivo
- Prompt colorizado con el nombre del agente
- Streaming de respuestas (carácter por carácter)
- Historial de comandos (readline)
- Auto-complete de capability names
- Muestra tool calls en tiempo real
- `/agent DevBot` para cambiar agente
- `/history` para ver historial
- `/clear` para limpiar

#### 2.4 Output formatting
```
$ python -m capabilityos chat "lista los archivos"

🤖 CapOS [agent mode]
├─ 🔧 filesystem_list_directory (L1)
│  path: C:\data\workspace
├─ ✔ 7 items found
└─ 📝 Tu workspace tiene 7 directorios: artifacts, memory, pagina...
```

### Archivos
| Archivo | Cambio |
|---------|--------|
| Nuevo: `capabilityos/__main__.py` | CLI entry point |
| Nuevo: `capabilityos/cli/chat.py` | Interactive chat |
| Nuevo: `capabilityos/cli/run.py` | Execute capability |
| Nuevo: `capabilityos/cli/status.py` | System status |
| Nuevo: `capabilityos/cli/serve.py` | Start server |
| Nuevo: `capabilityos/cli/formatter.py` | Colorized output |

---

## MÓDULO 3: VISUAL WORKFLOW BUILDER

### Problema
Las secuencias (sequences) se crean por texto. Los usuarios quieren arrastrar bloques visuales para crear flujos de trabajo.

### Solución

#### 3.1 UI — Canvas de nodos
```
┌─────────────────────────────────────────────────┐
│ Workflow: daily-report                    [Save] │
│                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ Trigger  │───→│ Read     │───→│ Send     │  │
│  │ Schedule │    │ Files    │    │ WhatsApp │  │
│  │ 09:00    │    │ *.log    │    │ summary  │  │
│  └──────────┘    └──────────┘    └──────────┘  │
│                        │                        │
│                        ▼                        │
│                  ┌──────────┐                   │
│                  │ If Error │                   │
│                  │ → Notify │                   │
│                  └──────────┘                   │
│                                                  │
│ Node palette:                                    │
│ [Trigger] [Tool] [Condition] [Loop] [Output]    │
└─────────────────────────────────────────────────┘
```

#### 3.2 Tipos de nodos
| Nodo | Función | Configuración |
|------|---------|---------------|
| **Trigger** | Inicia el workflow | schedule, webhook, manual |
| **Tool** | Ejecuta un tool | tool_id, params |
| **Agent** | Envía mensaje al agente | agent_id, message |
| **Condition** | If/else basado en resultado | expression, true_path, false_path |
| **Loop** | Repite sobre una lista | source, variable |
| **Transform** | Modifica datos | template, mapping |
| **Output** | Envía resultado | channel (whatsapp/telegram/UI), format |
| **Delay** | Espera tiempo | seconds |

#### 3.3 Modelo de datos
```json
{
  "id": "wf_daily_report",
  "name": "Daily Report",
  "nodes": [
    {"id": "n1", "type": "trigger", "config": {"schedule": "daily_09:00"}, "position": {"x": 100, "y": 100}},
    {"id": "n2", "type": "tool", "config": {"tool_id": "filesystem_list_directory", "params": {"path": "."}}, "position": {"x": 300, "y": 100}},
    {"id": "n3", "type": "output", "config": {"channel": "whatsapp", "template": "Files: {{n2.items.length}}"}, "position": {"x": 500, "y": 100}}
  ],
  "edges": [
    {"from": "n1", "to": "n2"},
    {"from": "n2", "to": "n3"}
  ]
}
```

#### 3.4 Librería de canvas
Usar **ReactFlow** (npm: `reactflow`) — librería estándar para node editors en React. Open source, bien documentada, performante.

#### 3.5 Ejecución
Los workflows se convierten a secuencias ejecutables por el SequenceRunner existente, o se ejecutan nodo por nodo via el AgentLoop.

### Archivos
| Archivo | Cambio |
|---------|--------|
| Nuevo: `frontend/app/src/components/workflow/WorkflowCanvas.jsx` | ReactFlow canvas |
| Nuevo: `frontend/app/src/components/workflow/NodePalette.jsx` | Drag palette |
| Nuevo: `frontend/app/src/components/workflow/NodeConfig.jsx` | Config panel |
| Nuevo: `frontend/app/src/components/workflow/nodes/*.jsx` | Custom node types |
| Nuevo: `frontend/app/src/pages/WorkflowEditor.jsx` | Page/route |
| Nuevo: `system/core/workflow/workflow_registry.py` | CRUD workflows |
| Nuevo: `system/core/workflow/workflow_executor.py` | Execute workflows |
| Nuevo: `handlers/workflow_handlers.py` | API endpoints |
| `App.jsx` | Nueva ruta /workflows |
| `api.js` | Workflow API functions |

---

## MÓDULO 4: MULTI-USUARIO

### Problema
El sistema no tiene autenticación. Cualquiera en la red local puede acceder.

### Solución

#### 4.1 Modelo de usuarios
```json
{
  "users": [
    {
      "id": "usr_owner",
      "username": "matias",
      "display_name": "Matias",
      "password_hash": "bcrypt_hash",
      "role": "owner",
      "created_at": "2026-03-30T..."
    },
    {
      "id": "usr_abc123",
      "username": "collaborator1",
      "display_name": "Juan",
      "password_hash": "bcrypt_hash",
      "role": "user",
      "permissions": {
        "workspaces": ["ws_123"],
        "agents": ["agt_default"],
        "max_security_level": 2,
        "can_create_agents": false,
        "can_create_skills": false,
        "can_access_supervisor": false
      },
      "created_at": "..."
    }
  ]
}
```

#### 4.2 Roles
| Rol | Permisos |
|-----|----------|
| **owner** | Todo — crear usuarios, supervisor, Level 3, todas las features |
| **admin** | Todo excepto crear owners y modificar supervisor config |
| **user** | Chat, ejecutar tools L1/L2, workspaces asignados, agentes asignados |
| **viewer** | Solo lectura — ver chats, historial, files |

#### 4.3 Autenticación
- **Login page** con username + password
- **JWT tokens** — generados al login, expiran en 24h
- **Session storage** — token en localStorage
- **API middleware** — verifica JWT en cada request
- **Refresh token** — auto-renovar antes de expirar
- Sin registro público — solo el owner crea usuarios

#### 4.4 Flujo
```
1. Usuario abre http://localhost:8000
2. Si no tiene token → Login page
3. Login: POST /auth/login {username, password} → {token, user}
4. Token guardado en localStorage
5. Cada request incluye: Authorization: Bearer {token}
6. API valida token y permisos
7. UI se adapta al rol (oculta features no permitidas)
```

#### 4.5 User Management UI
Control Center → Users (solo owner/admin):
- Lista de usuarios con rol y permisos
- Crear usuario con formulario
- Editar permisos: workspaces, agentes, security level
- Desactivar/eliminar usuario

### Archivos
| Archivo | Cambio |
|---------|--------|
| Nuevo: `system/core/auth/__init__.py` | Module |
| Nuevo: `system/core/auth/user_registry.py` | User CRUD + password hashing |
| Nuevo: `system/core/auth/jwt_service.py` | Token generation + validation |
| Nuevo: `system/core/auth/auth_middleware.py` | Request authentication |
| Nuevo: `handlers/auth_handlers.py` | Login, register, user management |
| Nuevo: `frontend/app/src/pages/Login.jsx` | Login page |
| Nuevo: `frontend/app/src/context/AuthContext.jsx` | Auth state management |
| `api_server.py` | Auth middleware, user routes |
| `docker-entrypoint.py` | Auth prefix |
| `App.jsx` | Auth guard, login redirect |
| `ControlCenter.jsx` | Users section |
| `sectionRegistry.js` | Users entry |

---

## ORDEN DE IMPLEMENTACIÓN

| # | Módulo | Esfuerzo | Dependencias |
|---|--------|----------|-------------|
| 1 | **Memoria Markdown** | Medio | Ninguna |
| 2 | **CLI Mode** | Medio | Ninguna |
| 3 | **Visual Workflow** | Alto | ReactFlow (npm) |
| 4 | **Multi-Usuario** | Alto | bcrypt/jwt (pip) |

Los módulos 1 y 2 son independientes y pueden hacerse en paralelo.
El módulo 3 requiere instalar ReactFlow.
El módulo 4 requiere instalar bcrypt y PyJWT.

## VERIFICACIÓN

### Módulo 1
- [ ] MEMORY.md se crea automáticamente con preferencias del usuario
- [ ] Daily notes se generan con resumen de actividad
- [ ] Auto-compaction se activa cuando contexto excede 80%
- [ ] Agente recuerda facts de sesiones anteriores

### Módulo 2
- [ ] `python -m capabilityos chat` abre prompt interactivo
- [ ] `python -m capabilityos chat "mensaje"` retorna respuesta
- [ ] `python -m capabilityos status` muestra health
- [ ] Tool calls se muestran con formato colorizado

### Módulo 3
- [ ] Canvas de nodos se renderiza con ReactFlow
- [ ] Drag & drop de nodos desde palette
- [ ] Conectar nodos con edges
- [ ] Configurar cada nodo
- [ ] Guardar workflow
- [ ] Ejecutar workflow → resultado visible

### Módulo 4
- [ ] Login page con username/password
- [ ] JWT token en cada request
- [ ] Owner puede crear usuarios
- [ ] User solo ve workspaces/agentes asignados
- [ ] Viewer no puede ejecutar tools
- [ ] Supervisor solo accesible para owner/admin
