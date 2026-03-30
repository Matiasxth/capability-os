# Plan: Completar Frontend — UIs faltantes para features implementados

## Problema
Hay 3 funcionalidades con backend completo y endpoints funcionales pero sin interfaz de usuario en el Control Center.

---

## 1. Workspace Health en Control Center → Workspaces

### Estado actual
- Los endpoints `/files/analyze/{ws_id}`, `/files/auto-clean/{ws_id}`, `/files/generate-readme/{ws_id}` funcionan
- La sección Workspaces en CC muestra lista con nombre, path, access, color
- No hay forma de analizar, limpiar o generar docs desde la UI

### Implementar
Agregar a cada workspace card:
- Botón **"Analyze"** → llama al endpoint, muestra resultados inline
- Issues con badges de severidad (high=rojo, medium=amarillo, low=gris)
- Suggestions como checklist
- Botón **"Auto-Clean"** → primero dry_run (preview), luego real con confirmación
- Botón **"Generate README"** → invoca Claude, muestra resultado en textarea editable
- Stats: total files, size, languages como mini badges

### Mockup
```
┌─ Workspace: Mi Proyecto ──────────────────────┐
│ 📁 C:\Users\...\mi-proyecto    ✏️ write       │
│                                                │
│ 142 files | 23.4 MB | Python 45, JS 30        │
│                                                │
│ Issues (3):                                    │
│ 🔴 HIGH: Hardcoded API key in config.py        │
│ 🟡 MED: No .gitignore                         │
│ 🟡 MED: No README.md                          │
│                                                │
│ Suggestions:                                   │
│ □ Move secret to .env                          │
│ □ Create .gitignore for Python                 │
│ □ Generate README                              │
│                                                │
│ [Analyze] [Auto-Clean] [Generate README]       │
└────────────────────────────────────────────────┘
```

### Archivos
- `ControlCenter.jsx` → modificar renderWorkspaces()
- `api.js` → analyzeWorkspace(wsId), autoCleanWorkspace(wsId, dryRun), generateReadme(wsId)

---

## 2. Skill Domains en Control Center → Skills

### Estado actual
- DomainRegistry crea dominios con SKILL.md y manifest
- Endpoint `/skills/auto-generated` lista skills creadas
- La sección Skills en CC muestra skills instaladas pero no dominios

### Implementar
Agregar sección "Auto-Generated Skill Domains":
- Lista de dominios con nombre, versión, tool count
- Expandir dominio → ver tools con descripción
- Badge "auto" para skills generadas por el supervisor
- SKILL.md preview colapsable

### Mockup
```
┌─ Skill Domains ────────────────────────────────┐
│ pdf_tools v1.0.2 (2 tools)              [▼]   │
│   📄 pdf_to_text — Extract text from PDF       │
│   📄 pdf_merge — Merge multiple PDFs           │
│                                                │
│ image_tools v1.0.0 (1 tool)             [▶]   │
└────────────────────────────────────────────────┘
```

### Archivos
- `ControlCenter.jsx` → modificar renderSkills() para incluir domains
- `api.js` → listDomains() (nuevo endpoint o usar /skills/auto-generated)

---

## 3. Scheduler UI en Control Center

### Estado actual
- TaskQueue con CRUD + ProactiveScheduler con 3 ciclos funcionan
- Endpoints: /scheduler/tasks (CRUD), /scheduler/status, /scheduler/log
- No hay UI para crear/ver/editar tareas

### Implementar
Nueva sección "Scheduler" en CC con:
- Status card: running, queue size, total executions
- Lista de tareas con toggle on/off
- Crear tarea: descripción, schedule (dropdown), agente (opcional), canal (opcional)
- Historial de ejecuciones recientes
- Botón "Run Now" por tarea

### Mockup
```
┌─ Scheduler ────────────────────────────────────┐
│ Status: ● Running | 2 tasks | 5 executions     │
│                                                │
│ Tasks:                                         │
│ ● Daily summary    18:00 daily    [Run] [Edit] │
│ ○ Health report    every 4h       [Run] [Edit] │
│                                                │
│ [+ Create Task]                                │
│                                                │
│ Recent Executions:                             │
│ 18:00 Daily summary → ✅ success (3.2s)        │
│ 14:00 Health report → ✅ success (1.1s)        │
└────────────────────────────────────────────────┘
```

### Crear tarea form:
- Descripción (input)
- Schedule: dropdown (every 30min, every hour, every 4h, daily 09:00, daily 18:00, daily 21:00)
- Agent: dropdown (opcional, lista de agentes)
- Channel: dropdown (opcional: none, whatsapp, telegram)
- Action message: textarea (qué le dices al agente)

### Archivos
- `ControlCenter.jsx` → nuevo renderScheduler()
- `sectionRegistry.js` → agregar "scheduler" (si no existe)
- `api.js` → listSchedulerTasks(), createSchedulerTask(), deleteSchedulerTask(), runTaskNow(), getSchedulerStatus(), getSchedulerLog()

---

## Orden de implementación

1. **API functions** en api.js (todas las funciones para los 3 módulos)
2. **Workspace Health** en renderWorkspaces() — más impactante visualmente
3. **Scheduler UI** en renderScheduler() — nueva sección
4. **Skill Domains** en renderSkills() — agregar sección de dominios

## Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `api.js` | ~15 funciones nuevas para workspace/scheduler/domains |
| `ControlCenter.jsx` | 3 secciones: workspace health, scheduler, domains |
| `sectionRegistry.js` | Agregar "scheduler" si no existe |

## Verificación
1. Workspace → click Analyze → muestra issues con colores
2. Workspace → Auto-Clean → preview → confirm → limpia
3. Workspace → Generate README → Claude genera → se muestra
4. Scheduler → Create Task → aparece en lista → Run Now funciona
5. Skills → Domains section muestra dominios auto-generados
