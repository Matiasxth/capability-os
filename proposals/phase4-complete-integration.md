# Plan Maestro: Integración Completa — Supervisor Full Powers + Visualizador + Skills por Dominio + Workspace Management

## Visión

Convertir CapOS en un sistema completamente autónomo donde:
- El Supervisor Claude puede crear, modificar y gestionar TODO el sistema
- Los usuarios tienen un IDE integrado para ver/editar código
- Las skills se organizan inteligentemente por dominio
- Los workspaces son gestionados activamente por el Supervisor

---

## MÓDULO 1: SUPERVISOR CON PODERES COMPLETOS

### 1.1 Arquitectura de Acciones

El Supervisor ya no solo conversa — ejecuta acciones reales a través de un protocolo de acciones JSON:

```
Usuario dice algo en el chat del Supervisor
     │
     ▼
SupervisorPromptBuilder construye mega-prompt con:
  - Estado completo del sistema (health, errors, tools, agents, skills)
  - Formato exacto de skills, agentes, config
  - Lista de acciones disponibles
  - Historial de la conversación
     │
     ▼
Claude CLI responde con JSON de acción:
  {"action": "create_skill", "spec": {...}}
  {"action": "create_agent", "spec": {...}}
  {"action": "edit_file", "path": "...", "content": "..."}
  {"action": "fix_config", "changes": {...}}
  {"action": "diagnose", "analysis": {...}}
  {"action": "restart_component", "component": "..."}
  {"action": "install_package", "package": "..."}
  {"action": "run_command", "command": "..."}
  {"action": "text", "message": "respuesta normal"}
     │
     ▼
ActionExecutor parsea y clasifica:
  - Acciones seguras (text, diagnose) → ejecuta directo
  - Acciones con preview (create_skill, create_agent, edit_file) → muestra preview
  - Acciones peligrosas (install_package, run_command, restart) → pide confirmación
     │
     ▼
Frontend renderiza según tipo:
  - text → mensaje normal en chat
  - skill_preview → card con código, botones Install/Edit/Discard
  - agent_preview → card con config, botones Create/Edit/Discard
  - file_preview → diff viewer con Apply/Discard
  - config_preview → cambios propuestos con Apply/Discard
  - command_preview → comando con Run/Cancel
  - diagnosis → análisis formateado con severity
```

### 1.2 Archivos a crear

**`system/core/supervisor/supervisor_prompt.py`**
- `build_mega_prompt(service)` — construye el prompt completo con:
  - Estado del sistema (health, security, errors, gaps)
  - Formato de skills (contract JSON + handler Python con ejemplo real)
  - Formato de agentes (todos los campos con ejemplo)
  - Lista de tools existentes (IDs agrupados por categoría)
  - Lista de agentes existentes
  - Configuración actual (LLM, browser, voice, etc.)
  - Últimos 5 errores
  - Instrucciones de cada acción con formato exacto

**`system/core/supervisor/action_executor.py`**
- `parse_action(response: str) → dict | None` — extrae JSON de acción
- `classify_action(action: dict) → "auto" | "preview" | "confirm"`
- `execute_auto(action, service) → result`
- `prepare_preview(action) → preview_data`
- `execute_approved(action, service) → result`

**`system/core/supervisor/file_manager.py`**
- `stage_file(path, content)` — guarda en zona staging
- `validate_python(code)` — compila para verificar syntax
- `validate_json(data, schema?)` — valida estructura
- `apply_staged(staged_id)` — mueve de staging a producción
- `discard_staged(staged_id)` — elimina staging

### 1.3 Zona de Staging

Todos los archivos que Claude genera van primero a una zona temporal:
```
workspace/staging/
├── stg_abc123/
│   ├── manifest.json       # qué se va a crear/modificar
│   ├── files/              # archivos generados
│   │   ├── contract.json
│   │   └── handler.py
│   └── validation.json     # resultado de validación automática
```

El sistema valida automáticamente:
- Python: `compile()` para verificar syntax
- JSON: `json.loads()` para estructura válida
- Imports: verificar que dependencias existen
- Security: escanear por patrones peligrosos (eval, exec, os.system)

Solo después de validación + aprobación del usuario se instala.

### 1.4 Frontend — Acciones en el Chat

Cada tipo de acción se renderiza diferente en el chat del Supervisor:

**Skill Preview Card**:
```
┌─────────────────────────────────────┐
│ 🔧 Nueva Skill: pdf_tools           │
│ Convierte y manipula archivos PDF    │
│                                      │
│ Tools: pdf_to_text, pdf_merge        │
│ Dependencies: PyPDF2                 │
│                                      │
│ ┌─ handler.py ─────────────────────┐│
│ │ def handle_pdf_to_text(params):  ││
│ │   path = params.get("path")      ││
│ │   ...                            ││
│ └──────────────────────────────────┘│
│                                      │
│ ✅ Syntax valid | 📦 1 dependency    │
│                                      │
│ [Install]  [Edit Code]  [Discard]    │
└─────────────────────────────────────┘
```

**Agent Preview Card**:
```
┌─────────────────────────────────────┐
│ 🤖 Nuevo Agente: DataBot            │
│ Experto en análisis de datos         │
│                                      │
│ Prompt: "You are DataBot..."         │
│ Tools: 5 seleccionados              │
│ Model: default | Lang: es            │
│                                      │
│ [Create]  [Edit]  [Discard]          │
└─────────────────────────────────────┘
```

**File Edit Preview**:
```
┌─────────────────────────────────────┐
│ 📝 Edit: system/tools/impl/x.py     │
│                                      │
│ - old line                           │
│ + new line                           │
│                                      │
│ [Apply]  [View Full]  [Discard]      │
└─────────────────────────────────────┘
```

**Command Preview**:
```
┌─────────────────────────────────────┐
│ ⚡ Command: pip install pandas       │
│ Security: Level 2 (confirmation)     │
│                                      │
│ [Run]  [Cancel]                      │
└─────────────────────────────────────┘
```

### 1.5 Endpoints nuevos

```
POST /supervisor/execute-action   → ejecuta acción aprobada
POST /supervisor/stage            → stage archivos para preview
GET  /supervisor/staged/{id}      → ver archivos staged
POST /supervisor/approve/{id}     → aprobar e instalar staged
POST /supervisor/discard/{id}     → descartar staged
```

---

## MÓDULO 2: SKILLS POR DOMINIO

### 2.1 Concepto

Las skills se organizan en dominios. Si ya existe un dominio, nuevos tools se agregan ahí:

```
workspace/skills/
├── pdf_tools/
│   ├── SKILL.md              # Descripción del dominio
│   ├── contracts/
│   │   ├── pdf_to_text.json
│   │   ├── pdf_merge.json
│   │   └── pdf_annotate.json
│   ├── handlers/
│   │   ├── pdf_to_text.py
│   │   ├── pdf_merge.py
│   │   └── pdf_annotate.py
│   └── manifest.json         # lista de tools, deps, versión
│
├── image_tools/
│   ├── contracts/
│   ├── handlers/
│   └── manifest.json
│
└── data_tools/
    ├── contracts/
    ├── handlers/
    └── manifest.json
```

### 2.2 Domain Registry

**`system/core/skills/domain_registry.py`**:
```python
class DomainRegistry:
    """Manages skill domains — groups of related tools."""

    def find_domain(self, description: str) -> str | None:
        """Find existing domain for a new tool."""
        # Uses keyword matching and LLM classification
        # "convert PDF" → "pdf_tools"
        # "resize image" → "image_tools"

    def create_domain(self, domain_id: str, name: str, description: str):
        """Create a new skill domain."""

    def add_tool_to_domain(self, domain_id: str, tool_spec: dict):
        """Add a tool to an existing domain."""

    def list_domains(self) -> list[dict]:
        """List all domains with their tools."""
```

### 2.3 Flujo de creación inteligente

```
1. Usuario o Supervisor quiere crear tool "pdf_to_text"
2. DomainRegistry.find_domain("convert PDF to text")
3. Si encuentra "pdf_tools" → agrega tool al dominio existente
4. Si no encuentra → crea nuevo dominio "pdf_tools" con este tool
5. Hot-load todos los tools del dominio
```

### 2.4 SKILL.md format

```markdown
---
domain: pdf_tools
name: PDF Tools
version: 1.2.0
description: Tools for creating, reading, and manipulating PDF files
author: supervisor
created: 2026-03-30
---

# PDF Tools

Handles all PDF-related operations:
- Convert documents to PDF
- Extract text from PDFs
- Merge multiple PDFs
- Annotate and sign PDFs

## Tools
- `pdf_to_text` — Extract text content from a PDF file
- `pdf_merge` — Combine multiple PDF files into one
- `pdf_annotate` — Add annotations to a PDF
```

---

## MÓDULO 3: VISUALIZADOR DE ARCHIVOS/CÓDIGO

### 3.1 Componentes

**FileExplorer** — árbol de archivos del workspace
- Navegar carpetas
- Iconos por tipo de archivo
- Right-click: crear, renombrar, eliminar, copiar
- Drag & drop para mover archivos
- Filtro de búsqueda

**CodeEditor** — editor de código con syntax highlighting
- Monaco Editor (el de VS Code) o CodeMirror
- Syntax highlighting para Python, JS, JSON, MD, HTML, CSS
- Line numbers, word wrap
- Search & replace
- Auto-indent
- Guardar con Ctrl+S (Level 2 — confirmación)

**PreviewPanel** — preview de archivos
- Markdown: renderizado
- HTML: iframe preview
- Imágenes: visor inline
- JSON: tree viewer colapsable
- CSV: tabla

**Terminal** — consola integrada
- Ejecutar comandos
- Output con colores ANSI
- Historial de comandos
- Autocompletar paths

**DiffViewer** — comparar cambios
- Side-by-side diff
- Inline diff
- Accept/reject per-line

### 3.2 Layout

Nueva ruta `/workspace/files` o tab en el Workspace:

```
┌──────────┬───────────────────────────┬──────────────┐
│ File     │ Tab1.py  Tab2.json  Tab3  │   Preview    │
│ Explorer │───────────────────────────│   Panel      │
│          │                           │              │
│ 📁 src   │  1 │ def hello():         │  ## README   │
│  📄 app  │  2 │   return "world"     │              │
│  📄 conf │  3 │                      │  This is...  │
│ 📁 tests │  4 │ def main():          │              │
│  📄 test │  5 │   print(hello())     │              │
│          │                           │              │
│          │───────────────────────────│──────────────│
│          │ Terminal                   │              │
│          │ $ python app.py           │              │
│          │ > world                   │              │
│          │ $                         │              │
└──────────┴───────────────────────────┴──────────────┘
```

### 3.3 Implementación

**Dependencia**: `monaco-editor` (npm package, el mismo de VS Code)

**Archivos nuevos**:
```
frontend/app/src/components/editor/
├── FileExplorer.jsx      # Árbol de archivos
├── CodeEditor.jsx        # Editor Monaco
├── PreviewPanel.jsx      # Preview de archivos
├── Terminal.jsx           # Consola integrada
├── DiffViewer.jsx         # Comparar cambios
├── TabBar.jsx             # Tabs de archivos abiertos
└── EditorLayout.jsx       # Layout principal
```

**API endpoints necesarios**:
```
GET  /files/tree/{workspace_id}              → árbol de archivos
GET  /files/read/{workspace_id}?path=...     → contenido de archivo
POST /files/write/{workspace_id}             → guardar archivo (Level 2)
POST /files/create/{workspace_id}            → crear archivo/carpeta (Level 2)
DELETE /files/delete/{workspace_id}?path=... → eliminar (Level 2/3)
POST /files/rename/{workspace_id}            → renombrar (Level 2)
POST /files/terminal/{workspace_id}          → ejecutar comando (Level 2)
```

### 3.4 Integración con el Supervisor

El Supervisor puede:
- Abrir archivos en el editor para que el usuario los revea
- Mostrar diffs de cambios propuestos
- El usuario edita directamente en el editor y el Supervisor ve los cambios
- Terminal compartida: el Supervisor puede sugerir comandos que el usuario ejecuta

---

## MÓDULO 4: SUPERVISOR EN WORKSPACES

### 4.1 Workspace Intelligence

El Supervisor analiza y gestiona activamente los workspaces:

**Auto-Structure** — cuando se crea un workspace:
```python
def suggest_structure(workspace_path, project_type):
    """Sugiere estructura de carpetas según el tipo de proyecto."""
    # "web" → src/, public/, tests/, .gitignore, README.md
    # "python" → src/, tests/, requirements.txt, setup.py
    # "data" → data/, notebooks/, reports/
```

**Health Check por Workspace**:
- Archivos sin usar (no referenciados)
- Archivos duplicados
- Archivos grandes que podrían estar en .gitignore
- Falta de .gitignore, README, tests
- API keys hardcoded en código
- TODO/FIXME pendientes

**Auto-Documentation**:
- Genera README.md basado en el contenido del proyecto
- Genera docstrings para funciones sin documentar
- Genera CHANGELOG basado en git log

**Auto-Clean**:
- Identifica y sugiere eliminar: __pycache__, node_modules (si hay otro), .tmp, logs viejos
- Sugiere mover archivos a mejor ubicación
- Detecta código muerto

### 4.2 Workspace Monitor

```python
class WorkspaceMonitor:
    """Monitorea cambios en workspaces activos."""

    def watch(self, workspace_id):
        """Observa cambios en el filesystem del workspace."""
        # Usa watchdog o polling para detectar cambios
        # Notifica al Supervisor cuando hay cambios relevantes

    def analyze(self, workspace_id) -> dict:
        """Análisis completo del workspace."""
        return {
            "total_files": N,
            "total_size": "X MB",
            "languages": {"python": 45, "javascript": 30, ...},
            "issues": [
                {"type": "missing_gitignore", "severity": "medium"},
                {"type": "hardcoded_key", "file": "config.py", "severity": "high"},
                {"type": "unused_file", "file": "old_backup.py", "severity": "low"},
            ],
            "suggestions": [
                "Add .gitignore for Python project",
                "Move API key to .env file",
                "Delete 3 unused files to save 2MB",
            ],
        }
```

### 4.3 Endpoints

```
GET  /workspaces/{id}/analyze     → análisis completo
GET  /workspaces/{id}/issues      → problemas detectados
POST /workspaces/{id}/auto-clean  → limpiar archivos innecesarios (Level 2)
POST /workspaces/{id}/auto-docs   → generar documentación (Level 2)
POST /workspaces/{id}/suggest-structure → sugerir estructura
```

---

## ORDEN DE IMPLEMENTACIÓN

### Fase A: Supervisor Full Powers (3 días)
1. `supervisor_prompt.py` — mega-prompt builder
2. `action_executor.py` — parser + clasificador + executor
3. `file_manager.py` — staging zone + validación
4. Modificar `supervisor_handlers.py` — usar mega-prompt + acciones
5. Endpoints approve/discard/stage
6. Frontend: renderizar acciones en chat (skill/agent/file/command previews)

### Fase B: Skills por Dominio (1 día)
7. `domain_registry.py` — find/create/add domains
8. Modificar `skill_creator.py` — usar domain registry
9. SKILL.md format + manifest.json
10. Frontend: sección Domains en Skills

### Fase C: Visualizador (3 días)
11. Instalar monaco-editor
12. `FileExplorer.jsx` — árbol de archivos
13. `CodeEditor.jsx` — editor con tabs
14. `PreviewPanel.jsx` — preview por tipo
15. `Terminal.jsx` — consola integrada
16. API endpoints /files/*
17. `EditorLayout.jsx` — layout con panels
18. Nueva ruta /workspace/editor

### Fase D: Workspace Management (2 días)
19. `WorkspaceMonitor` — análisis de workspace
20. Auto-structure suggestions
21. Issue detection (hardcoded keys, unused files, etc.)
22. Auto-documentation via Claude
23. API endpoints /workspaces/{id}/analyze, /issues, etc.
24. Frontend: sección Workspace Health en sidebar o CC

---

## ARCHIVOS A CREAR (total: ~25 archivos)

### Backend (12)
| Archivo | Módulo |
|---------|--------|
| `supervisor/supervisor_prompt.py` | 1 |
| `supervisor/action_executor.py` | 1 |
| `supervisor/file_manager.py` | 1 |
| `supervisor/workspace_monitor.py` | 4 |
| `skills/domain_registry.py` | 2 |
| `ui_bridge/handlers/file_handlers.py` | 3 |

### Frontend (10)
| Archivo | Módulo |
|---------|--------|
| `components/editor/FileExplorer.jsx` | 3 |
| `components/editor/CodeEditor.jsx` | 3 |
| `components/editor/PreviewPanel.jsx` | 3 |
| `components/editor/Terminal.jsx` | 3 |
| `components/editor/DiffViewer.jsx` | 3 |
| `components/editor/TabBar.jsx` | 3 |
| `components/editor/EditorLayout.jsx` | 3 |
| `components/supervisor/ActionCard.jsx` | 1 |
| `components/supervisor/SkillPreview.jsx` | 1 |
| `components/supervisor/AgentPreview.jsx` | 1 |

### Archivos a modificar (8)
| Archivo | Módulos |
|---------|---------|
| `supervisor/claude_bridge.py` | 1 |
| `supervisor/skill_creator.py` | 1, 2 |
| `handlers/supervisor_handlers.py` | 1 |
| `api_server.py` | 1, 2, 3, 4 |
| `ControlCenter.jsx` | 1, 2, 4 |
| `Workspace.jsx` | 3 |
| `App.jsx` | 3 |
| `api.js` | 1, 2, 3, 4 |

---

## VERIFICACIÓN

### Módulo 1
- [ ] Chat: "crea una skill para PDF" → preview con código → Install → hot-load funciona
- [ ] Chat: "crea un agente de datos" → preview → Create → aparece en agents
- [ ] Chat: "cambia el modelo a gpt-4o" → preview de config → Apply → settings cambia
- [ ] Chat: "instala pandas" → preview de comando → Run → pip install ejecuta
- [ ] Archivos en staging validados automáticamente antes de preview

### Módulo 2
- [ ] Crear tool "pdf_to_text" → dominio "pdf_tools" creado
- [ ] Crear tool "pdf_merge" → se agrega al dominio "pdf_tools" existente
- [ ] SKILL.md generado automáticamente con lista de tools
- [ ] Domains visibles en Control Center → Skills

### Módulo 3
- [ ] Abrir archivo desde FileExplorer → se muestra en CodeEditor
- [ ] Editar y guardar con Ctrl+S (pide confirmación)
- [ ] Preview de Markdown renderizado
- [ ] Terminal ejecuta comandos y muestra output
- [ ] Tabs para múltiples archivos
- [ ] Diff viewer muestra cambios propuestos

### Módulo 4
- [ ] Workspace analyze muestra issues (hardcoded keys, unused files)
- [ ] Auto-structure sugiere carpetas para proyecto nuevo
- [ ] Auto-clean identifica y limpia archivos innecesarios
- [ ] Auto-docs genera README basado en contenido del proyecto
- [ ] Supervisor notifica issues de workspace proactivamente
